"""Personal balance sheet and FIFO silver ledger."""

import argparse
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

from .api import AlpacaClient
from .config import Config
from .tools.alpaca_store import DEFAULT_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS wealth (
 id INTEGER PRIMARY KEY CHECK(id=1), real_estate REAL NOT NULL DEFAULT 0,
 liquid REAL NOT NULL DEFAULT 0, futures REAL NOT NULL DEFAULT 0,
 stocks REAL NOT NULL DEFAULT 0, cash REAL NOT NULL DEFAULT 0,
 real_estate_updated_at TEXT, liquid_updated_at TEXT, futures_updated_at TEXT,
 stocks_updated_at TEXT, cash_updated_at TEXT);
INSERT OR IGNORE INTO wealth(id) VALUES(1);
CREATE TABLE IF NOT EXISTS realEstate (
 id INTEGER PRIMARY KEY, device TEXT NOT NULL, purchase_price_cents INTEGER NOT NULL,
 source_file TEXT NOT NULL, source_row INTEGER NOT NULL, imported_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS silver_transactions (
 id INTEGER PRIMARY KEY, transaction_type TEXT NOT NULL CHECK(transaction_type IN ('purchase','sale')),
 troy_ounces REAL NOT NULL, total_cents INTEGER NOT NULL, transacted_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS silver_sale_allocations (
 sale_id INTEGER NOT NULL, purchase_id INTEGER NOT NULL, troy_ounces REAL NOT NULL,
 cost_basis_cents INTEGER NOT NULL, PRIMARY KEY(sale_id,purchase_id));
CREATE VIEW IF NOT EXISTS silver_lots AS SELECT p.id purchase_id,
 p.troy_ounces-COALESCE(SUM(a.troy_ounces),0) remaining_ounces,
 p.total_cents-COALESCE(SUM(a.cost_basis_cents),0) remaining_cost_basis_cents
 FROM silver_transactions p LEFT JOIN silver_sale_allocations a ON a.purchase_id=p.id
 WHERE p.transaction_type='purchase' GROUP BY p.id;
CREATE VIEW IF NOT EXISTS silver_position AS SELECT
 COALESCE(SUM(remaining_ounces),0) troy_ounces,
 COALESCE(SUM(remaining_cost_basis_cents),0) cost_basis_cents,
 COALESCE((SELECT SUM(s.total_cents-a.cost)
 FROM silver_transactions s JOIN (SELECT sale_id,SUM(cost_basis_cents) cost
 FROM silver_sale_allocations GROUP BY sale_id) a ON a.sale_id=s.id
 WHERE s.transaction_type='sale'),0) realized_pl_cents FROM silver_lots;
"""

DB = Path(os.getenv("FINANCE_DB_FILE", os.getenv("ALPACA_DATA_DB", str(DEFAULT_DB)))).expanduser()
STAMP = lambda: datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def cents(value):
    amount = Decimal(str(value).replace("$", "").replace(",", ""))
    if not amount.is_finite() or amount < 0 or amount * 100 != (amount * 100).to_integral_value():
        raise ValueError("amount must be a nonnegative dollar value with at most two decimals")
    return int(amount * 100)


def ods(path):
    ns = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
    text = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}p"
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    rows = []
    office = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
    for number, row in enumerate(root.findall(f".//{ns}table-row"), 1):
        cells = row.findall(f"{ns}table-cell")[:2]
        values = [c.get(office + "value") or " ".join("".join(p.itertext()).strip() for p in c.findall(text)) for c in cells]
        if len(values) == 2 and any(values):
            if not rows and values[0].casefold() in {"device", "item", "equipment", "description"}:
                continue
            rows.append((number, values[0], cents(values[1])))
    if not rows or any(not name for _, name, _ in rows):
        raise ValueError("ODS must contain equipment names and purchase prices in its first two columns")
    return rows


def equipment(args):
    path = Path(args.file).expanduser()
    rows = ods(path)
    with connect() as db:
        db.execute("DELETE FROM realEstate WHERE source_file <> 'manual'")
        db.executemany("INSERT INTO realEstate(device,purchase_price_cents,source_file,source_row,imported_at) VALUES(?,?,?,?,?)",
                       [(name, price, path.name, row, STAMP()) for row, name, price in rows])
        total = db.execute("SELECT SUM(purchase_price_cents) FROM realEstate").fetchone()[0] or 0
        db.execute("UPDATE wealth SET real_estate=?,real_estate_updated_at=? WHERE id=1", (total / 100, STAMP()))
    print(f"Imported {len(rows)} items; equipment value ${total / 100:,.2f}")


def equipment_add(args):
    with connect() as db:
        db.execute("INSERT INTO realEstate(device,purchase_price_cents,source_file,source_row,imported_at) VALUES(?,?, 'manual', (SELECT COUNT(*)+1 FROM realEstate WHERE source_file='manual'),?)",
                   (args.name, cents(args.price), STAMP()))
        total = db.execute("SELECT SUM(purchase_price_cents) FROM realEstate").fetchone()[0] or 0
        db.execute("UPDATE wealth SET real_estate=?,real_estate_updated_at=? WHERE id=1", (total / 100, STAMP()))
    print(f"Equipment value ${total / 100:,.2f}")


def silver(args):
    ounces, amount = Decimal(args.ounces), cents(args.amount)
    if not ounces.is_finite() or ounces <= 0:
        raise ValueError("ounces must be greater than zero")
    stamp = args.at or STAMP()
    with connect() as db:
        if args.side == "buy":
            db.execute("INSERT INTO silver_transactions(transaction_type,troy_ounces,total_cents,transacted_at) VALUES('purchase',?,?,?)", (float(ounces), amount, stamp))
        else:
            lots = db.execute("SELECT purchase_id,remaining_ounces,remaining_cost_basis_cents FROM silver_lots WHERE remaining_ounces>0 ORDER BY purchase_id").fetchall()
            if ounces > sum((Decimal(str(row["remaining_ounces"])) for row in lots), Decimal()):
                raise ValueError("sale exceeds the recorded silver balance")
            sale = db.execute("INSERT INTO silver_transactions(transaction_type,troy_ounces,total_cents,transacted_at) VALUES('sale',?,?,?)", (float(ounces), amount, stamp)).lastrowid
            left = ounces
            for lot in lots:
                available = Decimal(str(lot["remaining_ounces"]))
                used = min(left, available)
                cost = int(lot["remaining_cost_basis_cents"] if used == available else
                           (Decimal(lot["remaining_cost_basis_cents"]) * used / available).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                db.execute("INSERT INTO silver_sale_allocations VALUES(?,?,?,?)", (sale, lot["purchase_id"], float(used), cost))
                left -= used
                if not left:
                    break
        position = db.execute("SELECT * FROM silver_position").fetchone()
    print(f"Silver: {Decimal(str(position['troy_ounces'])):g} oz; cost basis ${position['cost_basis_cents']/100:,.2f}; realized P/L ${position['realized_pl_cents']/100:,.2f}")


def refresh(_args):
    cfg = Config.from_env()
    client = AlpacaClient(cfg.key_id, cfg.secret_key, cfg.trading_base)
    account, positions = client.account(), client.positions()
    bitcoin = sum(float(p.get("market_value", 0)) for p in positions if p.get("symbol", "").replace("/", "").upper() == "BTCUSD")
    stocks = sum(float(p.get("market_value", 0)) for p in positions if p.get("asset_class") == "us_equity")
    with connect() as db:
        equipment_value = (db.execute("SELECT SUM(purchase_price_cents) FROM realEstate").fetchone()[0] or 0) / 100
        silver_value = db.execute("SELECT troy_ounces FROM silver_position").fetchone()[0]
        if key := os.getenv("METALPRICE_API_KEY"):
            url = "https://api.metalpriceapi.com/v1/latest?" + urlencode({"api_key": key, "base": "USD", "currencies": "XAG"})
            with urlopen(Request(url, headers={"User-Agent":"df-fintechterm/1"}), timeout=20) as r:
                rates = json.load(r)["rates"]
            silver_value = silver_value * float(rates.get("USDXAG") or 1 / float(rates["XAG"]))
        values = (equipment_value, bitcoin, silver_value, stocks, float(account["cash"]))
        db.execute("UPDATE wealth SET real_estate=?,liquid=?,futures=?,stocks=?,cash=?,real_estate_updated_at=?,liquid_updated_at=?,futures_updated_at=?,stocks_updated_at=?,cash_updated_at=? WHERE id=1",
                   (*values, *([STAMP()] * 5)))
    show(_args)


def show(_args):
    with connect() as db:
        row = db.execute("SELECT * FROM wealth WHERE id=1").fetchone()
        silver_row = db.execute("SELECT * FROM silver_position").fetchone()
    fields = (("Equipment", row["real_estate"]), ("Bitcoin", row["liquid"]),
              ("Silver", row["futures"]), ("Stocks", row["stocks"]), ("Cash", row["cash"]))
    for name, value in fields:
        print(f"{name:10} ${value:,.2f}")
    print(f"{'Net worth':10} ${sum(value for _, value in fields):,.2f}")
    print(f"Silver lots: {Decimal(str(silver_row['troy_ounces'])):g} oz; basis ${silver_row['cost_basis_cents']/100:,.2f}; realized P/L ${silver_row['realized_pl_cents']/100:,.2f}")


def main():
    p = argparse.ArgumentParser(prog="df-fintechterm wealth")
    cmd = p.add_subparsers(dest="cmd", required=True)
    cmd.add_parser("show").set_defaults(run=show)
    cmd.add_parser("refresh").set_defaults(run=refresh)
    e = cmd.add_parser("equipment").add_subparsers(dest="equipment", required=True)
    x = e.add_parser("import"); x.add_argument("file"); x.set_defaults(run=equipment)
    x = e.add_parser("add"); x.add_argument("name"); x.add_argument("price"); x.set_defaults(run=equipment_add)
    s = cmd.add_parser("silver").add_subparsers(dest="side", required=True)
    for side in ("buy", "sell"):
        x = s.add_parser(side); x.add_argument("ounces"); x.add_argument("amount")
        x.add_argument("--at"); x.set_defaults(run=silver)
    a = p.parse_args()
    try: a.run(a)
    except (OSError, ValueError, sqlite3.Error, KeyError, InvalidOperation) as e: p.exit(2, f"wealth: {e}\n")


if __name__ == "__main__": main()
