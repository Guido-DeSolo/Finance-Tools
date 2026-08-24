from __future__ import annotations

import curses
from dataclasses import dataclass, field
import subprocess
import threading
import time
from typing import Any, Callable

from .analysis_view import load_active_analysis, seconds_old
from .api import AlpacaClient, ApiError, NewsClient, parse_timestamp
from .config import Config
from .finance_tools import FINANCE_TOOLS, FinanceTool, build_command
from .local_llm import LOCAL_LLM_MODEL, LocalLLM, LocalLLMError


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
    status: str = "Starting…"
    last_refresh: float = 0
    news_refreshed: float = 0
    news_scroll: int = 0
    ticker_offset: int = 0
    selected_order: int = 0
    right_pane: str = "news"
    chat: list[dict[str, str]] = field(default_factory=list)
    chat_busy: bool = False
    chat_scroll: int = 0
    main_view: str = "dashboard"
    analysis: list[dict[str, Any]] = field(default_factory=list)
    analysis_scroll: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class Terminal:
    def __init__(self, config: Config):
        self.config = config
        self.alpaca = AlpacaClient(config.key_id, config.secret_key, config.trading_base)
        self.news = NewsClient(config.newsdata_key)
        self.llm = LocalLLM()
        self.state = State(watchlist=list(config.watchlist))
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
        worker.start()
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

    def _refresh_loop(self) -> None:
        while not self.stop.is_set():
            analysis = load_active_analysis(self.config.finance_database)
            with self.state.lock:
                self.state.analysis = analysis
            try:
                with self.state.lock:
                    watch = list(self.state.watchlist)
                account = self.alpaca.account()
                positions = self.alpaca.positions()
                orders = self.alpaca.orders()
                symbols = sorted(set(watch + [p.get("symbol", "") for p in positions]) - {""})
                stocks = [x for x in symbols if "/" not in x and x != "BTCUSD"]
                snapshots = self.alpaca.stock_snapshots(stocks)
                try:
                    crypto = self.alpaca.crypto_snapshot()
                    book = self.alpaca.crypto_orderbook()
                except ApiError:
                    crypto, book = {}, {}
                now = time.time()
                news_items = None
                if self.config.newsdata_key and now - self.state.news_refreshed > 300:
                    news_items = self.news.latest()
                with self.state.lock:
                    self.state.account = account
                    self.state.positions = positions
                    self.state.orders = orders
                    self.state.snapshots = snapshots
                    self.state.crypto = crypto
                    self.state.book = book
                    self.state.last_refresh = now
                    if news_items is not None:
                        self.state.news = news_items
                        self.state.news_refreshed = now
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
        mode = "LIVE — REAL MONEY" if self.config.live else "PAPER"
        mode_attr = curses.color_pair(2) | curses.A_BOLD if self.config.live else curses.color_pair(1) | curses.A_BOLD
        self._safe_add(screen, 0, 0, f" DIXIE FLATLINE / ALPACA  [{mode}] ", mode_attr)
        age = f"{int(time.time()-s.last_refresh)}s" if s.last_refresh else "--"
        self._safe_add(screen, 0, max(0, w - len(status) - len(age) - 4), clip(f"{status} · {age}", w // 2), curses.A_DIM)
        if main_view == "analysis":
            self._draw_analysis(screen, h, w, analysis)
            screen.refresh()
            return
        equity = float(account.get("equity") or 0)
        last = float(account.get("last_equity") or equity or 0)
        pnl = equity - last
        pct = pnl / last * 100 if last else 0
        header = (f" EQUITY ${money(equity)}   TODAY ${money(pnl, True)} ({pct:+.2f}%)   "
                  f"CASH ${money(account.get('cash'))}   BUYING POWER ${money(account.get('buying_power'))}")
        self._safe_add(screen, 2, 0, header, curses.A_BOLD)

        split = max(46, int(w * .58))
        self._safe_add(screen, 4, 0, "POSITIONS", curses.color_pair(3) | curses.A_BOLD)
        self._safe_add(screen, 5, 0, "SYM       QTY       VALUE       AVG       NOW         P/L", curses.A_DIM)
        max_pos = max(3, min(8, (h - 12) // 2))
        for i, p in enumerate(positions[:max_pos]):
            row = (f"{p.get('symbol',''):<8} {number(p.get('qty')):>8} ${money(p.get('market_value')):>10} "
                   f"${money(p.get('avg_entry_price')):>8} ${money(p.get('current_price')):>9} "
                   f"${money(p.get('unrealized_pl'), True):>10}")
            attr = curses.color_pair(1) if float(p.get("unrealized_pl") or 0) >= 0 else curses.color_pair(2)
            self._safe_add(screen, 6 + i, 0, clip(row, split - 1), attr)

        order_y = 7 + max_pos
        self._safe_add(screen, order_y, 0, "RECENT ORDERS", curses.color_pair(3) | curses.A_BOLD)
        self._safe_add(screen, order_y + 1, 0, "  TIME          SYMBOL  SIDE  TYPE       QTY       STATUS", curses.A_DIM)
        order_rows = max(2, h - order_y - 5)
        for i, o in enumerate(orders[:order_rows]):
            qty = o.get("notional") and f"${number(o['notional'])}" or number(o.get("qty"))
            row = (f"{'> ' if i == s.selected_order else '  '}{parse_timestamp(o.get('submitted_at')):<13} "
                   f"{o.get('symbol',''):<7} {o.get('side',''):<5} {o.get('type',''):<10} {qty:>8}  {o.get('status','')}")
            attr = curses.A_REVERSE if i == s.selected_order else 0
            self._safe_add(screen, order_y + 2 + i, 0, clip(row, split - 1), attr)

        if right_pane == "chat":
            self._draw_chat(screen, split, h, w, chat, chat_busy)
        else:
            self._draw_news(screen, split, h, w, news)

        self._safe_add(screen, h - 3, 0, "[a] Live TA  [Tab] News/Chat  [Enter] Ask  [f] Tools  [b/s] Trade  [c] Cancel  [x] Close  [w] Watch  [q] Quit", curses.A_DIM)
        ticker = self._ticker_text()
        repeated = (ticker + "   ◆   ") * max(2, w // max(1, len(ticker)) + 2)
        offset = s.ticker_offset % max(1, len(ticker) + 7)
        view = (repeated + repeated)[offset:offset + w - 1]
        self._safe_add(screen, h - 1, 0, view, curses.color_pair(4) | curses.A_BOLD)
        screen.refresh()

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
                       " LIVE TECHNICAL ANALYSIS · watched order books · traded within 5m · newest first ",
                       curses.color_pair(3) | curses.A_BOLD)
        if not rows:
            self._safe_add(screen, 5, 2,
                           "No watched order-book symbols have received a trade in the last five minutes.",
                           curses.A_DIM)
            self._safe_add(screen, 7, 2,
                           "Start the live stream daemon and wait for trades to populate this view.")
        visible = max(1, (height - 8) // 3)
        max_scroll = max(0, len(rows) - visible)
        self.state.analysis_scroll = min(self.state.analysis_scroll, max_scroll)
        start = self.state.analysis_scroll
        for index, row in enumerate(rows[start:start + visible]):
            indicators = row.get("indicators") or {}
            age = seconds_old(row.get("updated_at"))
            age_text = "--" if age is None else (f"{age}s" if age < 60 else f"{age // 60}m")
            y = 4 + index * 3
            first = (
                f"{row.get('symbol', ''):<10} {age_text:>4}  bars {row.get('bars_buffered', 0):>3}  "
                f"RSI {self._indicator(indicators.get('rsi')):>7}  "
                f"ADX {self._indicator(indicators.get('adx')):>7}  "
                f"MACD {self._indicator(indicators.get('macd')):>8}  "
                f"SIG {self._indicator(indicators.get('macd_signal')):>8}  "
                f"HIST {self._indicator(indicators.get('macd_histogram')):>8}"
            )
            second = (
                f"{'':16}OBV {self._indicator(indicators.get('obv')):>9}  "
                f"ADL {self._indicator(indicators.get('adl')):>9}  "
                f"AROON↑ {self._indicator(indicators.get('aroon_up')):>7}  "
                f"AROON↓ {self._indicator(indicators.get('aroon_down')):>7}  "
                f"%K {self._indicator(indicators.get('stochastic_k')):>7}  "
                f"%D {self._indicator(indicators.get('stochastic_d')):>7}"
            )
            self._safe_add(screen, y, 1, clip(first, width - 2), curses.A_BOLD)
            self._safe_add(screen, y + 1, 1, clip(second, width - 2))
        position = f" · {start + 1}-{min(len(rows), start + visible)} of {len(rows)}" if rows else ""
        self._safe_add(screen, height - 2, 0,
                       f"[↑↓/jk] Scroll  [a] Dashboard  [f] Finance tools  [q] Quit{position}",
                       curses.A_DIM)

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
        self._safe_add(screen, 4, split, "NEWS  [Tab: local chat]",
                       curses.color_pair(3) | curses.A_BOLD)
        news_rows = height - 9
        if not self.config.newsdata_key:
            self._safe_add(screen, 6, split, "Set NEWSDATA_API_KEY to enable news.", curses.A_DIM)
        elif not news:
            self._safe_add(screen, 6, split, "Loading news…", curses.A_DIM)
        else:
            y = 5
            for item in news[self.state.news_scroll:]:
                when = (item.get("pubDate") or "")[:16]
                source = item.get("source_name") or item.get("source_id") or "News"
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
        title = f"LOCAL CHAT · {LOCAL_LLM_MODEL}  [Tab: news]"
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

    def _ticker_text(self) -> str:
        s = self.state
        items: list[str] = []
        crypto = s.crypto.get("BTC/USD") or s.crypto.get("BTCUSD") or {}
        quote = crypto.get("latestQuote") or {}
        trade = crypto.get("latestTrade") or {}
        book = s.book.get("BTC/USD") or s.book.get("BTCUSD") or {}
        bids, asks = book.get("bids") or [], book.get("asks") or []
        bid = (bids[0].get("p") if bids else None) or quote.get("bp")
        ask = (asks[0].get("p") if asks else None) or quote.get("ap")
        items.append(f"BTC/USD LAST {money(trade.get('p'))} BID {money(bid)} ASK {money(ask)}")
        for symbol in s.watchlist:
            snap = s.snapshots.get(symbol) or {}
            q, t = snap.get("latestQuote") or {}, snap.get("latestTrade") or {}
            daily, prev = snap.get("dailyBar") or {}, snap.get("prevDailyBar") or {}
            change = ((float(daily.get("c") or 0) / float(prev.get("c") or 1)) - 1) * 100 if prev else 0
            items.append(f"{symbol} LAST {money(t.get('p'))} BID {money(q.get('bp'))}×{number(q.get('bs'))} ASK {money(q.get('ap'))}×{number(q.get('as'))} {change:+.2f}%")
        return "   ◆   ".join(items)

    def _key(self, screen: Any, key: int) -> None:
        s = self.state
        if key in (ord("q"), 27):
            self.stop.set()
        elif key == ord("a"):
            s.main_view = "analysis" if s.main_view == "dashboard" else "dashboard"
            s.analysis_scroll = 0
        elif key == 9:
            s.right_pane = "chat" if s.right_pane == "news" else "news"
        elif key in (10, 13, curses.KEY_ENTER) and s.right_pane == "chat":
            self._chat_dialog(screen)
        elif key in (curses.KEY_DOWN, ord("j")):
            if s.main_view == "analysis":
                s.analysis_scroll = min(max(0, len(s.analysis) - 1), s.analysis_scroll + 1)
            elif s.right_pane == "chat":
                s.chat_scroll = max(0, s.chat_scroll - 1)
            else:
                s.news_scroll = min(max(0, len(s.news) - 1), s.news_scroll + 1)
        elif key in (curses.KEY_UP, ord("k")):
            if s.main_view == "analysis":
                s.analysis_scroll = max(0, s.analysis_scroll - 1)
            elif s.right_pane == "chat":
                s.chat_scroll += 1
            else:
                s.news_scroll = max(0, s.news_scroll - 1)
        elif key == ord("w"):
            symbol = self._prompt(screen, "Add/remove watched symbol: ").upper().strip()
            if symbol and all(c.isalnum() or c in ".-/" for c in symbol):
                with s.lock:
                    if symbol in s.watchlist:
                        s.watchlist.remove(symbol)
                    else:
                        s.watchlist.append(symbol)
        elif key == ord("f"):
            self._finance_menu(screen)
        elif key in (ord("b"), ord("s")):
            self._order_dialog(screen, "buy" if key == ord("b") else "sell")
        elif key == ord("c"):
            self._cancel_dialog(screen)
        elif key == ord("x"):
            self._close_dialog(screen)

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
            input("Press Enter to return to Dixie…")
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
        symbol = self._prompt(screen, f"{side.upper()} symbol: ").upper().strip()
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
        summary = f"{side.upper()} {qty} {symbol} {order_type}"
        if not self._confirm(screen, summary):
            self.state.status = "Order canceled locally"
            return
        if self.config.live and not self._confirm(screen, "REAL MONEY ORDER.", "LIVE"):
            self.state.status = "Live order canceled locally"
            return
        try:
            result = self.alpaca.place_order(order)
            self.state.status = f"Submitted {result.get('id', '')[:8]}: {summary}"
        except ApiError as exc:
            self.state.status = str(exc)

    def _cancel_dialog(self, screen: Any) -> None:
        open_orders = [o for o in self.state.orders if o.get("status") in {"new", "accepted", "pending_new", "partially_filled", "held"}]
        if not open_orders:
            self.state.status = "No cancelable orders"
            return
        token = self._prompt(screen, "Order ID prefix to cancel (see API IDs not displayed; 'latest' for newest): ").strip()
        matches = open_orders[:1] if token == "latest" else [o for o in open_orders if o.get("id", "").startswith(token)]
        if len(matches) != 1 or not self._confirm(screen, f"Cancel {matches[0].get('symbol')} order?"):
            self.state.status = "Cancel aborted: choose one valid order"
            return
        try:
            self.alpaca.cancel_order(matches[0]["id"])
            self.state.status = "Cancel requested"
        except ApiError as exc:
            self.state.status = str(exc)

    def _close_dialog(self, screen: Any) -> None:
        symbol = self._prompt(screen, "Position symbol to close: ").upper().strip()
        found = next((p for p in self.state.positions if p.get("symbol") == symbol), None)
        if not found or not self._confirm(screen, f"Close entire {symbol} position?"):
            self.state.status = "Close aborted"
            return
        if self.config.live and not self._confirm(screen, "REAL MONEY POSITION CLOSE.", "LIVE"):
            self.state.status = "Live close canceled locally"
            return
        try:
            self.alpaca.close_position(symbol)
            self.state.status = f"Close requested for {symbol}"
        except ApiError as exc:
            self.state.status = str(exc)
