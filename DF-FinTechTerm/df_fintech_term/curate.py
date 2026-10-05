"""Build plain-text research packets from stored market news."""

import argparse
import re
import sqlite3
from pathlib import Path

from .tools.alpaca_store import DEFAULT_DB


def main():
    p = argparse.ArgumentParser(prog="df-fintechterm news curate")
    p.add_argument("symbol"); p.add_argument("--output", type=Path); p.add_argument("--insider-days", type=int, default=7)
    a = p.parse_args(); symbol = a.symbol.upper().replace("/", "")
    if not re.fullmatch(r"[A-Z0-9._-]+", symbol): p.error("invalid symbol")
    path = Path(__import__("os").getenv("ALPACA_DATA_DB", DEFAULT_DB)).expanduser()
    if not path.is_file(): p.exit(2, f"news: database not found: {path}\n")
    if a.insider_days < 1: p.error("--insider-days must be positive")
    with sqlite3.connect(path) as db:
        rows = db.execute("""SELECT DISTINCT a.created_at,a.updated_at,a.headline,a.summary,a.content,a.source,a.url,
            EXISTS(SELECT 1 FROM news_article_symbols s WHERE s.article_id=a.article_id AND upper(replace(s.symbol,'/',''))=?)
            FROM news_articles a ORDER BY a.created_at DESC LIMIT 1000""", (symbol,)).fetchall()
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        insiders = db.execute("""SELECT filing_date,trade_date,ticker,company,insider,title,trade_type,price,quantity,trade_value,filing_url
            FROM insiders WHERE upper(replace(ticker,'/',''))=? AND datetime(filing_date)>=datetime('now',?)
            ORDER BY datetime(filing_date) DESC""", (symbol, f"-{a.insider_days} days")).fetchall() if "insiders" in tables else []
    token = re.compile(rf"(?<![A-Z0-9._-])\$?{re.escape(symbol)}(?![A-Z0-9._-])", re.I)
    rows = [r for r in rows if r[7] or token.search(" ".join(str(v or "") for v in r[2:5]))][:100]
    text = f"NEWS CONTEXT FOR {symbol}\nRECENT INSIDER TRADES (LAST {a.insider_days} DAYS)\n"
    text += "\n".join(" | ".join(str(v or "") for v in row) for row in insiders) or "No recorded insider trades."
    text += "\n\nNEWS ARTICLES\n" + "\n\n".join(f"{date} | {source or 'unknown'}\n{headline}\n{summary or ''}\n{content or ''}\n{url or ''}" for date, _, headline, summary, content, source, url, _ in rows)
    output = a.output or Path.home() / ".local/share/df-fintechterm/research" / f"{symbol}.txt"
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} articles to {output}")


if __name__ == "__main__": main()
