from __future__ import annotations

import curses
from dataclasses import dataclass, field
import shutil
import subprocess
import threading
import time
from typing import Any, Callable

from .analysis_view import load_active_analysis, seconds_old
from .api import AlpacaClient, ApiError, parse_timestamp
from .config import Config
from .finance_tools import FINANCE_TOOLS, FinanceTool, build_command
from .industry_view import load_industries, tickrs_command
from .ledger import Ledger, LedgerError
from .local_llm import LOCAL_LLM_MODEL, LocalLLM, LocalLLMError
from .news_feed import load_live_news, merge_news
from .openinsider_view import load_homepage
from .order_stream import OrderUpdateStream, merge_order, reconcile_orders
from .risk import assess_order, portfolio_risk_line
from .research_view import load_latest_research
from .symbol_view import load_symbol_profile, parse_command, sparkline
from .watchlist_view import load_stream_watchlist, unique_symbols


def money(value: Any, signed: bool = False) -> str:
    try:
        number = float(value)
        return f"{number:+,.2f}" if signed else f"{number:,.2f}"
    except (TypeError, ValueError):
        return "--"


def number(value: Any) -> str:
    try:
        return f"{float(value):,.4f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "--"


def clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


def sellable_symbols(positions: list[dict[str, Any]]) -> list[str]:
    """Return symbols representing positive holdings, never short positions."""
    result: set[str] = set()
    for position in positions:
        try:
            held = float(position.get("qty") or 0) > 0
        except (TypeError, ValueError):
            held = False
        symbol = str(position.get("symbol") or "").upper()
        if held and symbol:
            result.add(symbol)
    return sorted(result)


@dataclass
class State:
    account: dict[str, Any] = field(default_factory=dict)
    positions: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    news: list[dict[str, Any]] = field(default_factory=list)
    snapshots: dict[str, Any] = field(default_factory=dict)
    crypto: dict[str, Any] = field(default_factory=dict)
    book: dict[str, Any] = field(default_factory=dict)
    watchlist: list[str] = field(default_factory=list)
    watch_entries: list[dict[str, Any]] = field(default_factory=list)
    watchlist_selected: int = 0
    status: str = "Starting…"
    last_refresh: float = 0
    news_scroll: int = 0
    ticker_offset: int = 0
    ticker_view_scroll: int = 0
    selected_order: int = 0
    order_scroll: int = 0
    order_focus: bool = False
    order_stream_status: str = "Order stream starting"
    right_pane: str = "news"
    chat: list[dict[str, str]] = field(default_factory=list)
    chat_busy: bool = False
    chat_scroll: int = 0
    main_view: str = "dashboard"
    analysis: list[dict[str, Any]] = field(default_factory=list)
    analysis_scroll: int = 0
    industries: list[dict[str, Any]] = field(default_factory=list)
    industry_selected: int = 0
    industry_symbol_scroll: int = 0
    symbol: str = ""
    symbol_profile: dict[str, Any] = field(default_factory=dict)
    research: dict[str, Any] = field(default_factory=dict)
    research_busy: bool = False
    research_scroll: int = 0
    insider_homepage: dict[str, Any] = field(default_factory=dict)
    insider_scroll: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class Terminal:
    def __init__(self, config: Config):
        self.config = config
        self.alpaca = AlpacaClient(config.key_id, config.secret_key, config.trading_base)
        self.llm = LocalLLM()
        self.order_stream = OrderUpdateStream(
            config.key_id, config.secret_key, config.trading_base
        )
        self.ledger = Ledger(config.ledger_database, "live" if config.live else "paper")
        self.state = State()
        self.stop = threading.Event()

    def run(self) -> None:
        curses.wrapper(self._main)

    def _main(self, screen: Any) -> None:
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_CYAN, -1)
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        screen.timeout(100)
        worker = threading.Thread(target=self._refresh_loop, daemon=True)
        order_worker = threading.Thread(
            target=self.order_stream.run,
            args=(self.stop, self._receive_order_update, self._set_order_stream_status),
            daemon=True,
        )
        worker.start()
        order_worker.start()
        try:
            while not self.stop.is_set():
                self._draw(screen)
                key = screen.getch()
                if key != -1:
                    self._key(screen, key)
                if int(time.monotonic() * 4) % 2 == 0:
                    self.state.ticker_offset += 1
        finally:
            self.stop.set()
            worker.join(timeout=2)
            order_worker.join(timeout=2)

    def _set_order_stream_status(self, status: str) -> None:
        with self.state.lock:
            self.state.order_stream_status = status

    def _receive_order_update(self, update: dict[str, Any]) -> None:
        order = update["order"]
        event = str(update.get("event") or order.get("status") or "update")
        with self.state.lock:
            selected_id = None
            if self.state.orders:
                index = min(self.state.selected_order, len(self.state.orders) - 1)
                selected_id = self.state.orders[index].get("id")
            self.state.orders = merge_order(self.state.orders, order)
            self.state.selected_order = next(
                (i for i, item in enumerate(self.state.orders) if item.get("id") == selected_id), 0
            )
            self.state.order_stream_status = "Order stream connected"
            self.state.status = f"Order {event}: {order.get('symbol', '--')}"
        self._audit("broker", f"order_{event}", {"order": self._order_audit(order)})

    @staticmethod
    def _order_audit(order: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "id", "client_order_id", "symbol", "side", "type", "time_in_force",
            "qty", "notional", "limit_price", "stop_price", "status", "filled_qty",
            "filled_avg_price", "submitted_at", "updated_at",
        )
        return {key: order[key] for key in fields if order.get(key) is not None}

    def _audit(self, category: str, action: str, payload: dict[str, Any],
               required: bool = False) -> bool:
        try:
            self.ledger.record(category, action, payload)
            return True
        except LedgerError as error:
            if required:
                self.state.status = f"AUDIT BLOCK: {error}"
            return False

    def _refresh_loop(self) -> None:
        while not self.stop.is_set():
            analysis = load_active_analysis(self.config.finance_database)
            industries = load_industries(self.config.finance_database)
            live_news = load_live_news(self.config.finance_database)
            watch_entries = load_stream_watchlist(self.config.finance_database)
            with self.state.lock:
                workspace_symbol = self.state.symbol
            symbol_profile = (
                load_symbol_profile(self.config.finance_database, workspace_symbol)
                if workspace_symbol else {}
            )
            research = load_latest_research(self.config.research_directory)
            insider_homepage = load_homepage(self.config.openinsider_cache)
            with self.state.lock:
                self.state.analysis = analysis
                self.state.industries = industries
                self.state.industry_selected = min(
                    self.state.industry_selected, max(0, len(industries) - 1)
                )
                self.state.news = merge_news(live_news)
                self.state.watch_entries = watch_entries
                self.state.watchlist = unique_symbols(watch_entries)
                self.state.watchlist_selected = min(
                    self.state.watchlist_selected, max(0, len(watch_entries) - 1)
                )
                self.state.symbol_profile = symbol_profile
                self.state.research = research
                self.state.insider_homepage = insider_homepage
            try:
                with self.state.lock:
                    watch = unique_symbols(self.state.watch_entries, "stock")
                    crypto_watch = unique_symbols(self.state.watch_entries, "crypto")
                    selected = self.state.industry_selected
                    industry_symbols = (
                        [item["symbol"] for item in self.state.industries[selected]["symbols"]]
                        if self.state.industries else []
                    )
                    workspace_symbols = [self.state.symbol] if self.state.symbol else []
                    workspace_crypto = [item for item in workspace_symbols if "/" in item]
                account = self.alpaca.account()
                positions = self.alpaca.positions()
                orders = self.alpaca.orders()
                symbols = sorted(
                    set(watch + industry_symbols + workspace_symbols
                        + [p.get("symbol", "") for p in positions]) - {""}
                )
                stocks = [x for x in symbols if "/" not in x and x != "BTCUSD"]
                snapshots = self.alpaca.stock_snapshots(stocks)
                try:
                    crypto = self.alpaca.crypto_snapshots(sorted(set(crypto_watch + workspace_crypto)))
                    book = self.alpaca.crypto_orderbook()
                except ApiError:
                    crypto, book = {}, {}
                now = time.time()
                with self.state.lock:
                    self.state.account = account
                    self.state.positions = positions
                    self.state.orders = reconcile_orders(orders, self.state.orders)
                    self.state.selected_order = min(
                        self.state.selected_order, max(0, len(self.state.orders) - 1)
                    )
                    self.state.snapshots = snapshots
                    self.state.crypto = crypto
                    self.state.book = book
                    self.state.last_refresh = now
                    self.state.status = "Connected"
            except Exception as exc:
                with self.state.lock:
                    self.state.status = str(exc)[:160]
            self.stop.wait(self.config.refresh_seconds)

    def _safe_add(self, win: Any, y: int, x: int, text: str, attr: int = 0) -> None:
        height, width = win.getmaxyx()
        if 0 <= y < height and 0 <= x < width:
            try:
                win.addnstr(y, x, text, max(0, width - x - 1), attr)
            except curses.error:
                pass

    def _draw(self, screen: Any) -> None:
        screen.erase()
        h, w = screen.getmaxyx()
        if h < 20 or w < 80:
            self._safe_add(screen, 0, 0, "Terminal must be at least 80×20", curses.A_BOLD)
            screen.refresh()
            return
        s = self.state
        with s.lock:
            account, positions, orders = dict(s.account), list(s.positions), list(s.orders)
            news, status = list(s.news), s.status
            chat, right_pane, chat_busy = list(s.chat), s.right_pane, s.chat_busy
            main_view, analysis = s.main_view, list(s.analysis)
            industries = list(s.industries)
            watch_entries = list(s.watch_entries)
            symbol, symbol_profile = s.symbol, dict(s.symbol_profile)
            research, research_busy = dict(s.research), s.research_busy
            insider_homepage = dict(s.insider_homepage)
        mode = "LIVE — REAL MONEY" if self.config.live else "PAPER"
        mode_attr = curses.color_pair(2) | curses.A_BOLD if self.config.live else curses.color_pair(1) | curses.A_BOLD
        self._safe_add(screen, 0, 0, f" DF-FINTECHTERM  [{mode}] ", mode_attr)
        age = f"{int(time.time()-s.last_refresh)}s" if s.last_refresh else "--"
        self._safe_add(screen, 0, max(0, w - len(status) - len(age) - 4), clip(f"{status} · {age}", w // 2), curses.A_DIM)
        self._draw_main_tabs(screen, main_view)
        split = max(46, int(w * .58))
        content_height = h - 5
        if main_view == "research":
            self._draw_research(screen, content_height, split, research, research_busy)
        elif main_view == "insider":
            self._draw_openinsider(screen, content_height, split, insider_homepage)
        elif main_view == "symbol":
            self._draw_symbol_workspace(
                screen, content_height, split, symbol, symbol_profile,
                account, positions, orders, news,
            )
        elif main_view == "analysis":
            self._draw_analysis(screen, content_height, split, analysis)
        elif main_view == "industry":
            self._draw_industries(screen, content_height, split, industries)
        elif main_view == "ticker":
            self._draw_watch_ticker(screen, content_height, split, watch_entries)
        else:
            self._draw_dashboard(screen, content_height, split, account, positions, orders)

        for y in range(2, content_height):
            self._safe_add(screen, y, split - 1, "│", curses.A_DIM)
        if right_pane == "chat":
            self._draw_chat(screen, split, content_height, w, chat, chat_busy)
        elif right_pane == "watchlist":
            self._draw_watchlist(screen, split, content_height, w, watch_entries)
        else:
            self._draw_news(screen, split, content_height, w, news)

        ticker = self._ticker_text()
        repeated = (ticker + "   ◆   ") * max(2, w // max(1, len(ticker)) + 2)
        offset = s.ticker_offset % max(1, len(ticker) + 7)
        view = (repeated + repeated)[offset:offset + w - 1]
        self._safe_add(screen, content_height, 0, view, curses.color_pair(4) | curses.A_BOLD)
        self._draw_trade_panel(screen, h, w, account, positions)
        screen.refresh()

    def _draw_trade_panel(self, screen: Any, height: int, width: int,
                          account: dict[str, Any], positions: list[dict[str, Any]]) -> None:
        top = height - 4
        mode = "LIVE · REAL MONEY" if self.config.live else "PAPER"
        title = f" TRADE TICKET · {mode} "
        self._safe_add(screen, top, 0, "─" * (width - 1), curses.A_DIM)
        self._safe_add(screen, top, 1, title,
                       curses.color_pair(2 if self.config.live else 1) | curses.A_BOLD)
        held = sellable_symbols(positions)
        held_text = ", ".join(held) if held else "none"
        self._safe_add(screen, top + 1, 1,
                       clip(f"{portfolio_risk_line(account, positions)} · SELL: {held_text}", width - 2))
        self._safe_add(
            screen, top + 2, 1,
            clip("[b] BUY   [s] SELL   [o] Select orders   [c] Cancel selected   [x] Close position", width - 2),
            curses.A_BOLD,
        )
        self._safe_add(
            screen, top + 3, 1,
            clip("[:] Command  [Shift-Tab] Main view  [Tab] Right pane  [Enter] Chat  [f] Tools  [q] Quit", width - 2),
            curses.A_DIM,
        )

    def _draw_dashboard(self, screen: Any, height: int, width: int,
                        account: dict[str, Any], positions: list[dict[str, Any]],
                        orders: list[dict[str, Any]]) -> None:
        equity = float(account.get("equity") or 0)
        last = float(account.get("last_equity") or equity or 0)
        pnl = equity - last
        pct = pnl / last * 100 if last else 0
        header = (f" EQUITY ${money(equity)}   TODAY ${money(pnl, True)} ({pct:+.2f}%)   "
                  f"CASH ${money(account.get('cash'))}   BUYING POWER ${money(account.get('buying_power'))}")
        self._safe_add(screen, 2, 0, clip(header, width - 1), curses.A_BOLD)

        self._safe_add(screen, 4, 0, "POSITIONS", curses.color_pair(3) | curses.A_BOLD)
        self._safe_add(screen, 5, 0,
                       clip("SYM       QTY       VALUE       AVG       NOW         P/L", width - 1),
                       curses.A_DIM)
        max_pos = max(3, min(8, (height - 12) // 2))
        for i, p in enumerate(positions[:max_pos]):
            row = (f"{p.get('symbol',''):<8} {number(p.get('qty')):>8} ${money(p.get('market_value')):>10} "
                   f"${money(p.get('avg_entry_price')):>8} ${money(p.get('current_price')):>9} "
                   f"${money(p.get('unrealized_pl'), True):>10}")
            attr = curses.color_pair(1) if float(p.get("unrealized_pl") or 0) >= 0 else curses.color_pair(2)
            self._safe_add(screen, 6 + i, 0, clip(row, width - 1), attr)

        order_y = 7 + max_pos
        self._safe_add(screen, order_y, 0, "RECENT ORDERS", curses.color_pair(3) | curses.A_BOLD)
        stream = "LIVE" if self.state.order_stream_status == "Order stream connected" else "RECONNECT"
        focus = "ACTIVE" if self.state.order_focus else "press o"
        self._safe_add(screen, order_y, max(15, width - 27),
                       clip(f"{stream} · SELECT [{focus}]", 26), curses.A_DIM)
        self._safe_add(screen, order_y + 1, 0,
                       clip("  TIME          SYMBOL  SIDE  TYPE       QTY     FILLED     STATUS", width - 1),
                       curses.A_DIM)
        order_rows = max(2, height - order_y - 5)
        if self.state.selected_order < self.state.order_scroll:
            self.state.order_scroll = self.state.selected_order
        elif self.state.selected_order >= self.state.order_scroll + order_rows:
            self.state.order_scroll = self.state.selected_order - order_rows + 1
        self.state.order_scroll = min(
            self.state.order_scroll, max(0, len(orders) - order_rows)
        )
        start = self.state.order_scroll
        for row_number, o in enumerate(orders[start:start + order_rows]):
            i = start + row_number
            qty = o.get("notional") and f"${number(o['notional'])}" or number(o.get("qty"))
            filled = number(o.get("filled_qty"))
            selected = i == self.state.selected_order
            row = (f"{'▶ ' if selected else '  '}{parse_timestamp(o.get('submitted_at')):<13} "
                   f"{o.get('symbol',''):<7} {o.get('side',''):<5} {o.get('type',''):<10} "
                   f"{qty:>8} {filled:>8}  {o.get('status','')}")
            attr = curses.A_REVERSE if selected and self.state.order_focus else (curses.A_BOLD if selected else 0)
            self._safe_add(screen, order_y + 2 + row_number, 0, clip(row, width - 1), attr)

    def _draw_watch_ticker(self, screen: Any, height: int, width: int,
                           entries: list[dict[str, Any]]) -> None:
        self._safe_add(screen, 3, 0, clip(" PERSONAL WATCHLIST TICKER · daemon subscriptions ", width - 1),
                       curses.color_pair(3) | curses.A_BOLD)
        self._safe_add(screen, 5, 1, "SYMBOL       LAST        BID        ASK       CHANGE", curses.A_DIM)
        if not entries:
            self._safe_add(screen, 7, 2, "Watchlist is empty. Use the right Watchlist tab to add symbols.",
                           curses.A_DIM)
            return
        visible = max(1, height - 8)
        max_scroll = max(0, len(entries) - visible)
        self.state.ticker_view_scroll = min(self.state.ticker_view_scroll, max_scroll)
        start = self.state.ticker_view_scroll
        for y, entry in enumerate(entries[start:start + visible], 6):
            symbol = entry["symbol"]
            snapshots = self.state.crypto if entry["asset_class"] == "crypto" else self.state.snapshots
            snap = snapshots.get(symbol) or snapshots.get(symbol.replace("/", "")) or {}
            quote, trade = snap.get("latestQuote") or {}, snap.get("latestTrade") or {}
            daily, previous = snap.get("dailyBar") or {}, snap.get("prevDailyBar") or {}
            change = "--"
            if daily.get("c") is not None and previous.get("c"):
                change = f"{(float(daily['c']) / float(previous['c']) - 1) * 100:+.2f}%"
            row = (f"{symbol:<11} {money(trade.get('p')):>10} {money(quote.get('bp')):>10} "
                   f"{money(quote.get('ap')):>10} {change:>8}")
            self._safe_add(screen, y, 1, clip(row, width - 3))

    def _draw_main_tabs(self, screen: Any, selected: str) -> None:
        labels = (("dashboard", "DASHBOARD"), ("ticker", "TICKER"), ("industry", "INDUSTRY"),
                  ("analysis", "LIVE TA"))
        x = 1
        for value, label in labels:
            text = f" {label} "
            attr = curses.A_REVERSE | curses.A_BOLD if value == selected else curses.A_DIM
            self._safe_add(screen, 1, x, text, attr)
            x += len(text) + 1
        if selected == "symbol":
            self._safe_add(screen, 1, x, f" {self.state.symbol} ", curses.A_REVERSE | curses.A_BOLD)
        elif selected == "research":
            self._safe_add(screen, 1, x, " RESEARCH ", curses.A_REVERSE | curses.A_BOLD)
        elif selected == "insider":
            self._safe_add(screen, 1, x, " OPENINSIDER ", curses.A_REVERSE | curses.A_BOLD)

    def _draw_openinsider(
        self, screen: Any, height: int, width: int, homepage: dict[str, Any],
    ) -> None:
        trades = homepage.get("trades") or []
        stale = " · STALE CACHE" if homepage.get("stale") else ""
        self._safe_add(
            screen, 3, 1, clip(f"OPENINSIDER · HOMEPAGE FILINGS{stale}", width - 3),
            curses.color_pair(3) | curses.A_BOLD,
        )
        fetched = str(homepage.get("fetched_at") or "not fetched")[:19].replace("T", " ")
        self._safe_add(screen, 4, 1, clip(
            f"{len(trades)} documented rows · fetched {fetched} UTC", width - 3), curses.A_DIM)
        if homepage.get("error"):
            self._safe_add(screen, 5, 1, clip(f"Fetch warning: {homepage['error']}", width - 3),
                           curses.color_pair(2))
        if not trades:
            self._safe_add(screen, 7, 1, "No cached OpenInsider rows are available.", curses.A_DIM)
            return
        visible = max(1, (height - 8) // 2)
        self.state.insider_scroll = min(self.state.insider_scroll, max(0, len(trades) - visible))
        start = self.state.insider_scroll
        for index, trade in enumerate(trades[start:start + visible]):
            y = 6 + index * 2
            trade_type = str(trade.get("trade_type") or "--")
            trade_attr = (
                curses.color_pair(1) if trade_type.startswith("P")
                else curses.color_pair(2) if trade_type.startswith("S") else 0
            )
            first = (
                f"{str(trade.get('filing_date') or '')[:16]}  {trade.get('ticker', '--'):<7} "
                f"{trade_type:<12} {trade.get('value', '--'):>12}"
            )
            second = (
                f" {trade.get('section', '--')} · {trade.get('insider', '--')} · "
                f"{trade.get('quantity', '--')} @ {trade.get('price', '--')}"
            )
            self._safe_add(screen, y, 1, clip(first, width - 3), trade_attr)
            self._safe_add(screen, y + 1, 1, clip(second, width - 3), curses.A_DIM)
        self._safe_add(screen, height - 1, 1, clip(
            f"[u] View  [↑↓/jk] Scroll · {start + 1}-{min(len(trades), start + visible)} of {len(trades)}",
            width - 3), curses.A_BOLD)

    def _draw_research(
        self, screen: Any, height: int, width: int,
        research: dict[str, Any], busy: bool,
    ) -> None:
        self._safe_add(screen, 3, 1, "DAILY RESEARCH · LOCAL LLM", curses.color_pair(3) | curses.A_BOLD)
        if busy:
            self._safe_add(screen, 4, 1, "Generating validated evidence, summary, and notebook…", curses.A_BOLD)
        elif not research:
            self._safe_add(screen, 4, 1, "No publication yet. Press g to generate today's research.", curses.A_DIM)
        else:
            self._safe_add(screen, 4, 1, clip(
                f"{research.get('generated_at')} · {research.get('model')} · "
                f"{research.get('candidate_count')} candidates", width - 3), curses.A_DIM)
            self._safe_add(screen, 5, 1, clip(
                f"SYMBOLS: {', '.join(research.get('symbols') or [])}", width - 3))
            self._safe_add(screen, 6, 1, clip(
                f"NOTEBOOK: {research.get('notebook_path')}", width - 3), curses.A_DIM)
            lines: list[str] = []
            for paragraph in str(research.get("summary") or "").splitlines():
                lines.extend(self._wrap(paragraph, max(5, width - 3)) or [""])
            visible = max(1, height - 9)
            self.state.research_scroll = min(
                self.state.research_scroll, max(0, len(lines) - visible)
            )
            for offset, line in enumerate(lines[self.state.research_scroll:self.state.research_scroll + visible]):
                self._safe_add(screen, 8 + offset, 1, line)
        self._safe_add(screen, max(3, height - 1), 1,
                       "[g] Generate publication  [↑↓/jk] Scroll", curses.A_BOLD)

    def _draw_symbol_workspace(
        self, screen: Any, height: int, width: int, symbol: str,
        profile: dict[str, Any], account: dict[str, Any],
        positions: list[dict[str, Any]], orders: list[dict[str, Any]],
        news: list[dict[str, Any]],
    ) -> None:
        asset = profile.get("asset") or {}
        classification = profile.get("classification") or {}
        snap = self.state.crypto.get(symbol) or self.state.snapshots.get(symbol) or {}
        quote, trade = snap.get("latestQuote") or {}, snap.get("latestTrade") or {}
        position = next((item for item in positions if item.get("symbol") == symbol), {})
        self._safe_add(screen, 3, 1, clip(
            f"{symbol} · {asset.get('name') or classification.get('company_name') or 'Unknown security'}",
            width - 3), curses.color_pair(3) | curses.A_BOLD)
        self._safe_add(screen, 4, 1, clip(
            f"LAST ${money(trade.get('p') or position.get('current_price'))}   "
            f"BID ${money(quote.get('bp'))}   ASK ${money(quote.get('ap'))}   "
            f"EXCHANGE {asset.get('exchange') or '--'}", width - 3), curses.A_BOLD)
        self._safe_add(screen, 5, 1, clip(
            f"SECTOR {classification.get('sector') or '--'} · "
            f"INDUSTRY {classification.get('industry') or '--'} · "
            f"TRADABLE {'yes' if asset.get('tradable') else 'unknown/no'} · "
            f"FRACTIONAL {'yes' if asset.get('fractionable') else 'no'}", width - 3), curses.A_DIM)

        bars = profile.get("bars") or []
        closes = [float(item["close"]) for item in bars if item.get("close") is not None]
        self._safe_add(screen, 7, 1, "STORED PRICE HISTORY", curses.A_BOLD)
        self._safe_add(screen, 8, 1, sparkline(closes, max(1, width - 3)), curses.color_pair(1))
        if closes:
            self._safe_add(screen, 9, 1, clip(
                f"{bars[-1].get('timeframe', '--')} · {len(closes)} bars · "
                f"low ${min(closes):,.2f} · high ${max(closes):,.2f} · last ${closes[-1]:,.2f}",
                width - 3), curses.A_DIM)
        else:
            self._safe_add(screen, 9, 1, "No stored bars; use Finance Tools → Alpaca download history.", curses.A_DIM)

        analysis = profile.get("analysis") or {}
        self._safe_add(screen, 11, 1, "TECHNICAL", curses.A_BOLD)
        technical = "  ".join(
            f"{key.upper()} {self._indicator(analysis.get(key))}"
            for key in ("rsi", "adx", "macd", "signal", "stochastic_k")
        )
        self._safe_add(screen, 12, 1, clip(technical or "No stored analysis", width - 3))

        self._safe_add(screen, 14, 1, "ACCOUNT CONTEXT", curses.A_BOLD)
        open_orders = [item for item in orders if item.get("symbol") == symbol and item.get("status") in {
            "new", "accepted", "pending_new", "partially_filled", "held",
        }]
        self._safe_add(screen, 15, 1, clip(
            f"POSITION {number(position.get('qty'))} · VALUE ${money(position.get('market_value'))} · "
            f"P/L ${money(position.get('unrealized_pl'), True)} · OPEN ORDERS {len(open_orders)}",
            width - 3))

        self._safe_add(screen, 17, 1, "SYMBOL NEWS", curses.A_BOLD)
        tagged = profile.get("news") or [item for item in news if symbol in item.get("symbols", [])]
        for offset, item in enumerate(tagged[:max(0, height - 19)]):
            title = item.get("headline") or item.get("title") or "Untitled"
            self._safe_add(screen, 18 + offset, 1, clip(
                f"{str(item.get('updated_at') or item.get('timestamp') or '')[:16]} · {title}",
                width - 3))

    def _draw_industries(self, screen: Any, height: int, width: int,
                         industries: list[dict[str, Any]]) -> None:
        self._safe_add(screen, 3, 0, clip(" TICKER INDUSTRY VIEW · Alpaca universe ", width - 1),
                       curses.color_pair(3) | curses.A_BOLD)
        if not industries:
            self._safe_add(screen, 6, 2, "No classified industries with stored market data.",
                           curses.A_DIM)
            self._safe_add(screen, 8, 2, "Run Finance Tools → Classification · refresh.")
        else:
            selected = min(self.state.industry_selected, len(industries) - 1)
            visible_industries = min(5, max(2, (height - 12) // 2))
            start = min(max(0, selected - visible_industries + 1),
                        max(0, len(industries) - visible_industries))
            self._safe_add(screen, 4, 1, "INDUSTRIES", curses.A_DIM)
            for y, index in enumerate(range(start, min(len(industries), start + visible_industries)), 5):
                item = industries[index]
                label = f"{item['industry']} ({len(item['symbols'])})"
                attr = curses.A_REVERSE if index == selected else 0
                self._safe_add(screen, y, 1, clip(label, width - 3), attr)

            item = industries[selected]
            detail_y = 6 + visible_industries
            self._safe_add(screen, detail_y, 1, clip(
                f"{item['industry']} · {item.get('sector') or 'Unspecified sector'}", width - 3
            ), curses.A_BOLD)
            self._safe_add(screen, detail_y + 1, 1,
                           "SYMBOL      LAST       BID       ASK      CHG", curses.A_DIM)
            visible_symbols = max(1, height - detail_y - 5)
            max_scroll = max(0, len(item["symbols"]) - visible_symbols)
            self.state.industry_symbol_scroll = min(self.state.industry_symbol_scroll, max_scroll)
            for y, symbol_item in enumerate(
                item["symbols"][self.state.industry_symbol_scroll:
                                self.state.industry_symbol_scroll + visible_symbols], detail_y + 2
            ):
                symbol = symbol_item["symbol"]
                snap = self.state.snapshots.get(symbol) or {}
                quote, trade = snap.get("latestQuote") or {}, snap.get("latestTrade") or {}
                daily, previous = snap.get("dailyBar") or {}, snap.get("prevDailyBar") or {}
                change = "--"
                if daily.get("c") is not None and previous.get("c"):
                    change = f"{(float(daily['c']) / float(previous['c']) - 1) * 100:+.2f}%"
                row = (f"{symbol:<8} {money(trade.get('p')):>9} {money(quote.get('bp')):>9} "
                       f"{money(quote.get('ap')):>9} {change:>7}")
                self._safe_add(screen, y, 1, clip(row, width - 3))
        self._safe_add(screen, height - 2, 0,
                       clip("[t] tickrs  [PgUp/PgDn] constituents", width - 1), curses.A_DIM)

    @staticmethod
    def _indicator(value: Any) -> str:
        if value is None:
            return "--"
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "--"
        magnitude = abs(numeric)
        if magnitude >= 1_000_000_000:
            return f"{numeric / 1_000_000_000:.2f}B"
        if magnitude >= 1_000_000:
            return f"{numeric / 1_000_000:.2f}M"
        if magnitude >= 1_000:
            return f"{numeric / 1_000:.2f}K"
        return f"{numeric:.2f}"

    def _draw_analysis(self, screen: Any, height: int, width: int,
                       rows: list[dict[str, Any]]) -> None:
        self._safe_add(screen, 2, 0,
                       clip(" LIVE TECHNICAL ANALYSIS · active within 5m · newest first ", width - 1),
                       curses.color_pair(3) | curses.A_BOLD)
        if not rows:
            self._safe_add(screen, 5, 2,
                           clip("No watched order-book symbols traded in the last five minutes.", width - 4),
                           curses.A_DIM)
            self._safe_add(screen, 7, 2,
                           clip("Start the live stream daemon and wait for trades.", width - 4))
        visible = max(1, (height - 9) // 4)
        max_scroll = max(0, len(rows) - visible)
        self.state.analysis_scroll = min(self.state.analysis_scroll, max_scroll)
        start = self.state.analysis_scroll
        for index, row in enumerate(rows[start:start + visible]):
            indicators = row.get("indicators") or {}
            age = seconds_old(row.get("updated_at"))
            age_text = "--" if age is None else (f"{age}s" if age < 60 else f"{age // 60}m")
            y = 4 + index * 4
            first = (
                f"{row.get('symbol', ''):<10} {age_text:>4}  bars {row.get('bars_buffered', 0):>3}  "
            )
            second = (
                f" RSI {self._indicator(indicators.get('rsi')):>6}  "
                f"ADX {self._indicator(indicators.get('adx')):>7}  "
                f"MACD {self._indicator(indicators.get('macd')):>7}"
            )
            third = (
                f"SIG {self._indicator(indicators.get('macd_signal')):>8}  "
                f"HIST {self._indicator(indicators.get('macd_histogram')):>7}  "
                f"OBV {self._indicator(indicators.get('obv')):>7}"
            )
            fourth = (
                f"ADL {self._indicator(indicators.get('adl')):>7}  "
                f"AR {self._indicator(indicators.get('aroon_up'))}/{self._indicator(indicators.get('aroon_down'))}  "
                f"STO {self._indicator(indicators.get('stochastic_k'))}/{self._indicator(indicators.get('stochastic_d'))}"
            )
            self._safe_add(screen, y, 1, clip(first, width - 2), curses.A_BOLD)
            self._safe_add(screen, y + 1, 1, clip(second, width - 2))
            self._safe_add(screen, y + 2, 1, clip(third, width - 2))
            self._safe_add(screen, y + 3, 1, clip(fourth, width - 2))
        position = f"{start + 1}-{min(len(rows), start + visible)} of {len(rows)}" if rows else ""
        self._safe_add(screen, height - 2, 0, clip(position, width - 1), curses.A_DIM)

    @staticmethod
    def _wrap(text: str, width: int, max_lines: int | None = 3) -> list[str]:
        if width < 5:
            return []
        words, lines, current = text.split(), [], ""
        for word in words:
            if len(current) + len(word) + 1 > width:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            lines.append(current)
        return lines if max_lines is None else lines[:max_lines]

    def _draw_news(self, screen: Any, split: int, height: int, width: int,
                   news: list[dict[str, Any]]) -> None:
        self._safe_add(screen, 4, split, "LIVE NEWS · ALPACA + NEWSDATA  [Tab: next]",
                       curses.color_pair(3) | curses.A_BOLD)
        news_rows = height - 9
        if not news:
            self._safe_add(screen, 6, split, "Waiting for live news…", curses.A_DIM)
            self._safe_add(screen, 7, split,
                           "Start the Alpaca stream or configure NEWSDATA_API_KEY.", curses.A_DIM)
        else:
            y = 5
            for item in news[self.state.news_scroll:]:
                when = parse_timestamp(item.get("timestamp"))
                source = f"{item.get('provider', 'News')}:{item.get('source', 'News')}"
                title = " ".join((item.get("title") or "Untitled").split())
                lines = self._wrap(f"{when} · {source} — {title}", width - split - 2)
                if y + len(lines) > 5 + news_rows:
                    break
                for line in lines:
                    self._safe_add(screen, y, split, line)
                    y += 1
                y += 1

    def _draw_chat(self, screen: Any, split: int, height: int, width: int,
                   messages: list[dict[str, str]], busy: bool) -> None:
        title = f"LOCAL CHAT · {LOCAL_LLM_MODEL}  [Tab: next]"
        self._safe_add(screen, 4, split, clip(title, width - split - 1),
                       curses.color_pair(3) | curses.A_BOLD)
        available = max(1, height - 9)
        pane_width = width - split - 2
        lines: list[tuple[str, int]] = []
        if not messages:
            lines.append(("Press Enter to talk to the fixed local model.", curses.A_DIM))
        for message in messages:
            role = "YOU" if message.get("role") == "user" else "LLM"
            attr = curses.A_BOLD if role == "YOU" else 0
            wrapped = self._wrap(
                f"{role}: {message.get('content', '')}", pane_width, max_lines=None
            )
            lines.extend((line, attr) for line in wrapped)
            lines.append(("", 0))
        if busy:
            lines.append(("LLM: thinking…", curses.A_DIM))
        end = max(0, len(lines) - self.state.chat_scroll)
        start = max(0, end - available)
        for y, (line, attr) in enumerate(lines[start:end], 5):
            self._safe_add(screen, y, split, line, attr)

    def _draw_watchlist(self, screen: Any, split: int, height: int, width: int,
                        entries: list[dict[str, Any]]) -> None:
        self._safe_add(screen, 4, split, "WATCHLIST · LIVE DAEMON  [Tab: next]",
                       curses.color_pair(3) | curses.A_BOLD)
        self._safe_add(screen, 5, split, "  CLASS   SYMBOL       FEED / LOCATION", curses.A_DIM)
        if not entries:
            self._safe_add(screen, 7, split, "No live subscriptions. Press + to add one.", curses.A_DIM)
        visible = max(1, height - 9)
        selected = min(self.state.watchlist_selected, max(0, len(entries) - 1))
        start = min(max(0, selected - visible + 1), max(0, len(entries) - visible))
        for y, index in enumerate(range(start, min(len(entries), start + visible)), 6):
            item = entries[index]
            route = item.get("feed") or item.get("location") or "default"
            marker = "▶" if index == selected else " "
            row = f"{marker} {item['asset_class']:<7} {item['symbol']:<12} {route}"
            self._safe_add(screen, y, split, clip(row, width - split - 1),
                           curses.A_REVERSE if index == selected else 0)
        self._safe_add(screen, height - 2, split,
                       clip("[+] Add  [d] Remove selected  [↑↓] Select", width - split - 1),
                       curses.A_DIM)

    def _ticker_text(self) -> str:
        s = self.state
        items: list[str] = []
        for entry in s.watch_entries:
            symbol = entry["symbol"]
            source = s.crypto if entry["asset_class"] == "crypto" else s.snapshots
            snap = source.get(symbol) or source.get(symbol.replace("/", "")) or {}
            q, t = snap.get("latestQuote") or {}, snap.get("latestTrade") or {}
            daily, prev = snap.get("dailyBar") or {}, snap.get("prevDailyBar") or {}
            change = ((float(daily.get("c") or 0) / float(prev.get("c") or 1)) - 1) * 100 if prev else 0
            items.append(f"{symbol} LAST {money(t.get('p'))} BID {money(q.get('bp'))}×{number(q.get('bs'))} ASK {money(q.get('ap'))}×{number(q.get('as'))} {change:+.2f}%")
        return "   ◆   ".join(items) if items else "WATCHLIST EMPTY · open the right Watchlist tab and press +"

    def _key(self, screen: Any, key: int) -> None:
        s = self.state
        if key == 27 and s.order_focus:
            s.order_focus = False
        elif key in (ord("q"), 27):
            self.stop.set()
        elif key == ord("o") and s.main_view == "dashboard":
            s.order_focus = not s.order_focus
            s.selected_order = min(s.selected_order, max(0, len(s.orders) - 1))
            s.status = "Order selection active" if s.order_focus else "Order selection closed"
        elif s.order_focus and key in (curses.KEY_DOWN, ord("j")):
            s.selected_order = min(max(0, len(s.orders) - 1), s.selected_order + 1)
        elif s.order_focus and key in (curses.KEY_UP, ord("k")):
            s.selected_order = max(0, s.selected_order - 1)
        elif key == ord(":"):
            self._command_dialog(screen)
        elif key == ord("r"):
            s.main_view = "research" if s.main_view != "research" else "dashboard"
            s.order_focus = False
            s.research_scroll = 0
        elif key == ord("u"):
            s.main_view = "insider" if s.main_view != "insider" else "dashboard"
            s.order_focus = False
            s.insider_scroll = 0
        elif key == ord("g") and s.main_view == "research":
            self._generate_daily_research()
        elif key == ord("a"):
            s.main_view = "analysis" if s.main_view == "dashboard" else "dashboard"
            s.analysis_scroll = 0
        elif key == ord("i"):
            s.main_view = "industry" if s.main_view != "industry" else "dashboard"
            s.industry_symbol_scroll = 0
        elif key == curses.KEY_BTAB:
            views = ("dashboard", "ticker", "industry", "analysis")
            s.main_view = (
                views[(views.index(s.main_view) + 1) % len(views)]
                if s.main_view in views else "dashboard"
            )
        elif key == 9:
            panes = ("news", "chat", "watchlist")
            s.right_pane = panes[(panes.index(s.right_pane) + 1) % len(panes)]
        elif key in (10, 13, curses.KEY_ENTER) and s.right_pane == "chat":
            self._chat_dialog(screen)
        elif key == ord("t") and s.main_view == "industry":
            self._open_industry_ticker(screen)
        elif key in (curses.KEY_DOWN, ord("j")):
            if s.main_view == "research":
                s.research_scroll += 1
            elif s.main_view == "insider":
                visible = max(1, len(s.insider_homepage.get("trades") or []) - 1)
                s.insider_scroll = min(visible, s.insider_scroll + 1)
            elif s.right_pane == "watchlist":
                s.watchlist_selected = min(max(0, len(s.watch_entries) - 1),
                                           s.watchlist_selected + 1)
            elif s.main_view == "analysis":
                s.analysis_scroll = min(max(0, len(s.analysis) - 1), s.analysis_scroll + 1)
            elif s.main_view == "industry":
                s.industry_selected = min(max(0, len(s.industries) - 1),
                                          s.industry_selected + 1)
                s.industry_symbol_scroll = 0
            elif s.right_pane == "chat":
                s.chat_scroll = max(0, s.chat_scroll - 1)
            else:
                s.news_scroll = min(max(0, len(s.news) - 1), s.news_scroll + 1)
        elif key in (curses.KEY_UP, ord("k")):
            if s.main_view == "research":
                s.research_scroll = max(0, s.research_scroll - 1)
            elif s.main_view == "insider":
                s.insider_scroll = max(0, s.insider_scroll - 1)
            elif s.right_pane == "watchlist":
                s.watchlist_selected = max(0, s.watchlist_selected - 1)
            elif s.main_view == "analysis":
                s.analysis_scroll = max(0, s.analysis_scroll - 1)
            elif s.main_view == "industry":
                s.industry_selected = max(0, s.industry_selected - 1)
                s.industry_symbol_scroll = 0
            elif s.right_pane == "chat":
                s.chat_scroll += 1
            else:
                s.news_scroll = max(0, s.news_scroll - 1)
        elif key == curses.KEY_NPAGE and s.main_view == "industry":
            s.industry_symbol_scroll += 10
        elif key == curses.KEY_PPAGE and s.main_view == "industry":
            s.industry_symbol_scroll = max(0, s.industry_symbol_scroll - 10)
        elif key == curses.KEY_NPAGE and s.main_view == "ticker":
            s.ticker_view_scroll += 10
        elif key == curses.KEY_PPAGE and s.main_view == "ticker":
            s.ticker_view_scroll = max(0, s.ticker_view_scroll - 10)
        elif key in (ord("+"), ord("w")) and s.right_pane == "watchlist":
            self._add_watchlist_dialog(screen)
        elif key == ord("d") and s.right_pane == "watchlist":
            self._remove_watchlist_selected()
        elif key == ord("w"):
            s.right_pane = "watchlist"
        elif key == ord("f"):
            self._finance_menu(screen)
        elif key in (ord("b"), ord("s")):
            self._order_dialog(screen, "buy" if key == ord("b") else "sell")
        elif key == ord("c"):
            self._cancel_dialog(screen)
        elif key == ord("x"):
            self._close_dialog(screen)

    def _open_industry_ticker(self, screen: Any) -> None:
        if not self.state.industries:
            self.state.status = "No classified industry is selected"
            return
        if shutil.which("tickrs") is None:
            self.state.status = "tickrs is not installed; install tickrs to open the industry interface"
            return
        selected = min(self.state.industry_selected, len(self.state.industries) - 1)
        industry = self.state.industries[selected]
        command = tickrs_command(industry)
        curses.def_prog_mode()
        curses.endwin()
        try:
            result = subprocess.run(command, check=False)
            self.state.status = (
                f"tickrs · {industry['industry']}: closed" if result.returncode == 0
                else f"tickrs · {industry['industry']}: exited {result.returncode}"
            )
        except OSError as error:
            self.state.status = f"Could not run tickrs: {error}"
        finally:
            curses.reset_prog_mode()
            curses.curs_set(0)
            screen.timeout(100)
            screen.clear()

    def _command_dialog(self, screen: Any) -> None:
        text = self._prompt(
            screen, "Command [SYMBOL | DASH | ORDERS | WATCH | TICKER | INDUSTRY | TA | RESEARCH | INSIDERS]: "
        ).strip()
        try:
            command = parse_command(text)
        except ValueError as error:
            self.state.status = f"Command error: {error}"
            return
        if command.destination == "watchlist":
            self.state.right_pane = "watchlist"
            self.state.status = "Watchlist opened"
            return
        self.state.main_view = command.destination
        self.state.order_focus = command.focus_orders
        if command.symbol:
            self.state.symbol = command.symbol
            self.state.symbol_profile = load_symbol_profile(
                self.config.finance_database, command.symbol
            )
            self.state.status = f"Symbol workspace: {command.symbol}"
        else:
            self.state.status = f"View: {command.destination}"

    def _generate_daily_research(self) -> None:
        with self.state.lock:
            if self.state.research_busy:
                self.state.status = "Daily research generation is already running"
                return
            self.state.research_busy = True
            self.state.status = "Generating daily research…"
        threading.Thread(target=self._daily_research_worker, daemon=True).start()

    def _daily_research_worker(self) -> None:
        launcher = self.config.finance_shell.parent.parent / "run.sh"
        try:
            result = subprocess.run(
                [str(launcher), "action", "daily-research", "--output-dir",
                 str(self.config.research_directory)],
                check=False, capture_output=True, text=True,
            )
            with self.state.lock:
                if result.returncode == 0:
                    self.state.research = load_latest_research(self.config.research_directory)
                    self.state.research_scroll = 0
                    self.state.status = "Daily research notebook published"
                else:
                    detail = (result.stderr or result.stdout).strip().splitlines()
                    self.state.status = f"Daily research failed: {(detail[-1] if detail else 'unknown error')[:120]}"
        except OSError as error:
            with self.state.lock:
                self.state.status = f"Daily research failed: {error}"
        finally:
            with self.state.lock:
                self.state.research_busy = False

    def _stream_watchlist_command(self, action: str, entry: dict[str, str]) -> bool:
        command = [
            str(self.config.finance_shell), "alpaca", "stream", "--db",
            str(self.config.finance_database), action, entry["symbol"],
            "--class", entry["asset_class"],
        ]
        if entry["asset_class"] == "stock" and entry.get("feed"):
            command.extend(("--feed", entry["feed"]))
        if entry["asset_class"] == "crypto" and entry.get("location"):
            command.extend(("--location", entry["location"]))
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
        except OSError as error:
            self.state.status = f"Watchlist update failed: {error}"
            return False
        message = (result.stdout or result.stderr).strip().splitlines()
        self.state.status = message[-1][:160] if message else f"Watchlist {action}: exit {result.returncode}"
        if result.returncode != 0:
            return False
        entries = load_stream_watchlist(self.config.finance_database)
        with self.state.lock:
            self.state.watch_entries = entries
            self.state.watchlist = unique_symbols(entries)
            self.state.watchlist_selected = min(
                self.state.watchlist_selected, max(0, len(entries) - 1)
            )
        return True

    def _add_watchlist_dialog(self, screen: Any) -> None:
        symbol = self._prompt(screen, "Watch symbol (stocks AAPL; crypto BTC/USD): ").upper().strip()
        if not symbol or not all(character.isalnum() or character in ".-/" for character in symbol):
            self.state.status = "Watchlist add aborted: invalid symbol"
            return
        inferred = "crypto" if "/" in symbol else "stock"
        asset_class = self._prompt(screen, f"Asset class [stock/crypto] ({inferred}): ").strip().lower()
        asset_class = asset_class or inferred
        if asset_class not in {"stock", "crypto"}:
            self.state.status = "Watchlist add aborted: class must be stock or crypto"
            return
        self._stream_watchlist_command("add", {"symbol": symbol, "asset_class": asset_class})

    def _remove_watchlist_selected(self) -> None:
        with self.state.lock:
            if not self.state.watch_entries:
                self.state.status = "Watchlist is already empty"
                return
            index = min(self.state.watchlist_selected, len(self.state.watch_entries) - 1)
            entry = dict(self.state.watch_entries[index])
        self._stream_watchlist_command("remove", entry)

    def _prompt(self, screen: Any, label: str, secret: bool = False) -> str:
        h, w = screen.getmaxyx()
        if secret:
            curses.noecho()
        else:
            curses.echo()
        curses.curs_set(1)
        self._safe_add(screen, h - 3, 0, " " * (w - 1))
        self._safe_add(screen, h - 3, 0, label, curses.A_BOLD)
        screen.refresh()
        try:
            raw = screen.getstr(h - 3, min(len(label), w - 2), max(1, w - len(label) - 2))
            return raw.decode("utf-8", "replace")
        finally:
            curses.noecho()
            curses.curs_set(0)

    def _confirm(self, screen: Any, text: str, required: str = "YES") -> bool:
        return self._prompt(screen, clip(f"{text} Type {required}: ", screen.getmaxyx()[1] - len(required) - 3)) == required

    def _chat_dialog(self, screen: Any) -> None:
        with self.state.lock:
            if self.state.chat_busy:
                self.state.status = "Local LLM is still responding"
                return
        prompt = self._prompt(screen, "Local chat: ").strip()
        if not prompt:
            return
        with self.state.lock:
            self.state.chat.append({"role": "user", "content": prompt})
            history = list(self.state.chat[-20:])
            self.state.chat_busy = True
            self.state.chat_scroll = 0
        threading.Thread(target=self._chat_request, args=(history,), daemon=True).start()

    def _chat_request(self, history: list[dict[str, str]]) -> None:
        try:
            reply = self.llm.chat(history)
            with self.state.lock:
                self.state.chat.append({"role": "assistant", "content": reply})
                self.state.status = f"Local LLM replied ({LOCAL_LLM_MODEL})"
        except LocalLLMError as error:
            with self.state.lock:
                self.state.chat.append({"role": "assistant", "content": f"Error: {error}"})
                self.state.status = str(error)
        finally:
            with self.state.lock:
                self.state.chat_busy = False

    def _finance_menu(self, screen: Any) -> None:
        """Display every Finance Shell tool and run the selected operation."""
        selected = 0
        while not self.stop.is_set():
            screen.erase()
            height, width = screen.getmaxyx()
            if height < 10 or width < 60:
                self._safe_add(screen, 0, 0, "Finance menu requires at least 60×10", curses.A_BOLD)
                screen.refresh()
                key = screen.getch()
                if key in (27, ord("q"), ord("f")):
                    return
                continue
            self._safe_add(screen, 0, 0, " FINANCE SHELL · ALL TOOLS ", curses.color_pair(3) | curses.A_BOLD)
            self._safe_add(screen, 1, 0, f"Dispatcher: {self.config.finance_shell}", curses.A_DIM)
            visible = max(1, height - 5)
            start = min(max(0, selected - visible + 1), max(0, len(FINANCE_TOOLS) - visible))
            for row, index in enumerate(range(start, min(len(FINANCE_TOOLS), start + visible)), 3):
                tool = FINANCE_TOOLS[index]
                marker = "▶" if index == selected else " "
                suffix = f"  [{tool.arguments}]" if tool.arguments else ""
                attr = curses.A_REVERSE if index == selected else 0
                self._safe_add(screen, row, 1, clip(f"{marker} {tool.title}{suffix}", width - 3), attr)
            self._safe_add(screen, height - 1, 0,
                           "[↑↓/jk] Select  [Enter] Run  [Esc/q/f] Dashboard", curses.A_DIM)
            screen.refresh()
            key = screen.getch()
            if key in (27, ord("q"), ord("f")):
                return
            if key in (curses.KEY_DOWN, ord("j")):
                selected = min(len(FINANCE_TOOLS) - 1, selected + 1)
            elif key in (curses.KEY_UP, ord("k")):
                selected = max(0, selected - 1)
            elif key in (curses.KEY_NPAGE,):
                selected = min(len(FINANCE_TOOLS) - 1, selected + visible)
            elif key in (curses.KEY_PPAGE,):
                selected = max(0, selected - visible)
            elif key in (10, 13, curses.KEY_ENTER):
                tool = FINANCE_TOOLS[selected]
                arguments = ""
                if tool.arguments:
                    arguments = self._prompt(screen, f"Arguments ({tool.arguments}; blank allowed): ").strip()
                self._run_finance_tool(screen, tool, arguments)

    def _run_finance_tool(self, screen: Any, tool: FinanceTool, arguments: str) -> None:
        fsh = self.config.finance_shell
        if not fsh.is_file():
            self.state.status = f"Finance Shell not found: {fsh}"
            return
        try:
            command = build_command(fsh, tool, arguments)
        except ValueError as error:
            self.state.status = f"Invalid arguments: {error}"
            return
        curses.def_prog_mode()
        curses.endwin()
        try:
            print(f"\nFinance Shell · {tool.title}\n$ {' '.join(command)}\n")
            result = subprocess.run(command, check=False)
            print(f"\nExited with status {result.returncode}.")
            input("Press Enter to return to DF-FinTechTerm…")
            self.state.status = (
                f"{tool.title}: complete" if result.returncode == 0
                else f"{tool.title}: exited {result.returncode}"
            )
        except OSError as error:
            self.state.status = f"Could not run Finance Shell: {error}"
        finally:
            curses.reset_prog_mode()
            curses.curs_set(0)
            screen.timeout(100)
            screen.clear()

    def _order_dialog(self, screen: Any, side: str) -> None:
        allowed: list[str] = []
        if side == "sell":
            with self.state.lock:
                allowed = sellable_symbols(list(self.state.positions))
            if not allowed:
                self.state.status = "SELL unavailable: account has no positive holdings"
                return
            label = f"SELL held symbol [{','.join(allowed)}]: "
        else:
            label = "BUY symbol (any Alpaca-supported asset): "
        symbol = self._prompt(screen, label).upper().strip()
        if side == "sell" and symbol not in allowed:
            self.state.status = f"SELL blocked: {symbol or '--'} is not a positive account holding"
            return
        qty = self._prompt(screen, "Quantity (or prefix dollars with $): ").strip()
        order_type = self._prompt(screen, "Type [market/limit/stop/stop_limit]: ").strip().lower() or "market"
        if not symbol or not qty or order_type not in {"market", "limit", "stop", "stop_limit"}:
            self.state.status = "Order aborted: invalid input"
            return
        order: dict[str, Any] = {"symbol": symbol, "side": side, "type": order_type, "time_in_force": "day"}
        if qty.startswith("$"):
            order["notional"] = qty[1:]
        else:
            order["qty"] = qty
        if order_type in {"limit", "stop_limit"}:
            order["limit_price"] = self._prompt(screen, "Limit price: ").strip()
        if order_type in {"stop", "stop_limit"}:
            order["stop_price"] = self._prompt(screen, "Stop price: ").strip()
        with self.state.lock:
            account = dict(self.state.account)
            positions = list(self.state.positions)
            source = self.state.crypto if "/" in symbol else self.state.snapshots
            snapshot = dict(source.get(symbol) or source.get(symbol.replace("/", "")) or {})
        if not snapshot:
            try:
                fetched = (
                    self.alpaca.crypto_snapshots([symbol])
                    if "/" in symbol else self.alpaca.stock_snapshots([symbol])
                )
                snapshot = dict(fetched.get(symbol) or fetched.get(symbol.replace("/", "")) or {})
            except ApiError:
                snapshot = {}
        assessment = assess_order(
            order, account, positions, snapshot, self.config.risk_limits
        )
        audit = {
            "order": self._order_audit(order),
            "risk": {
                "allowed": assessment.allowed,
                "estimated_notional": str(assessment.estimated_notional) if assessment.estimated_notional is not None else None,
                "reference_price": str(assessment.reference_price) if assessment.reference_price is not None else None,
                "projected_position_pct": str(assessment.projected_position_pct) if assessment.projected_position_pct is not None else None,
                "projected_buying_power": str(assessment.projected_buying_power) if assessment.projected_buying_power is not None else None,
                "warnings": assessment.warnings,
                "violations": assessment.violations,
            },
        }
        if not assessment.allowed:
            self._audit("decision", "order_blocked", audit)
            self.state.status = f"RISK BLOCK: {'; '.join(assessment.violations)}"
            return
        summary = f"{side.upper()} {qty} {symbol} {order_type}"
        if not self._confirm(screen, f"{summary} · {assessment.summary()}"):
            self._audit("decision", "order_declined", audit)
            self.state.status = "Order canceled locally"
            return
        if self.config.live and not self._confirm(screen, "REAL MONEY ORDER.", "LIVE"):
            self._audit("decision", "live_order_declined", audit)
            self.state.status = "Live order canceled locally"
            return
        if not self._audit("decision", "order_authorized", audit, required=True):
            return
        try:
            result = self.alpaca.place_order(order)
            self._audit("broker", "order_submitted", {
                "request": self._order_audit(order), "response": self._order_audit(result),
            })
            self.state.status = f"Submitted {result.get('id', '')[:8]}: {summary}"
        except ApiError as exc:
            self._audit("broker", "order_submission_failed", {
                "request": self._order_audit(order), "error": str(exc),
            })
            self.state.status = str(exc)

    def _cancel_dialog(self, screen: Any) -> None:
        with self.state.lock:
            selected = (
                dict(self.state.orders[min(self.state.selected_order, len(self.state.orders) - 1)])
                if self.state.orders else None
            )
        cancelable = {"new", "accepted", "pending_new", "partially_filled", "held"}
        if not selected or selected.get("status") not in cancelable:
            self.state.status = "Selected order is not cancelable"
            return
        detail = f"{selected.get('side', '').upper()} {selected.get('symbol', '--')} {selected.get('type', '')}"
        if not self._confirm(screen, f"Cancel selected {detail} order?"):
            self._audit("decision", "cancel_declined", {"order": self._order_audit(selected)})
            self.state.status = "Cancel aborted"
            return
        self._audit("decision", "cancel_authorized", {"order": self._order_audit(selected)})
        try:
            self.alpaca.cancel_order(selected["id"])
            self._audit("broker", "cancel_requested", {"order": self._order_audit(selected)})
            self.state.status = f"Cancel requested for {selected.get('symbol', '--')}"
        except ApiError as exc:
            self._audit("broker", "cancel_failed", {
                "order": self._order_audit(selected), "error": str(exc),
            })
            self.state.status = str(exc)

    def _close_dialog(self, screen: Any) -> None:
        symbol = self._prompt(screen, "Position symbol to close: ").upper().strip()
        found = next((p for p in self.state.positions if p.get("symbol") == symbol), None)
        if not found or not self._confirm(screen, f"Close entire {symbol} position?"):
            if found:
                self._audit("decision", "close_declined", {"symbol": symbol})
            self.state.status = "Close aborted"
            return
        if self.config.live and not self._confirm(screen, "REAL MONEY POSITION CLOSE.", "LIVE"):
            self._audit("decision", "live_close_declined", {"symbol": symbol})
            self.state.status = "Live close canceled locally"
            return
        self._audit("decision", "close_authorized", {
            "symbol": symbol, "qty": found.get("qty"), "market_value": found.get("market_value"),
        })
        try:
            self.alpaca.close_position(symbol)
            self._audit("broker", "close_requested", {"symbol": symbol})
            self.state.status = f"Close requested for {symbol}"
        except ApiError as exc:
            self._audit("broker", "close_failed", {"symbol": symbol, "error": str(exc)})
            self.state.status = str(exc)
