"""Blue Kite, a fake online shop that lives in one SQLite file: state/shop.db."""

import os
import sqlite3
from pathlib import Path

# All people and data here are fictional.
CUSTOMERS = [  # id, name, email, address
    ("C-101", "Anna Silva", "anna.silva@example.com", "12 Lake Road, Toronto"),
    ("C-102", "David Lee", "david.lee@example.com", "8 Hill Street, Ottawa"),
    ("C-103", "David Lee", "david.k.lee@example.com", "45 River Lane, Montreal"),
]
ORDERS = [  # id, customer, status, api_times_out
    ("O-5001", "C-101", "shipped", 0),
    ("O-5002", "C-102", "delivered", 0),
    ("O-5003", "C-103", "delivered", 0),
    ("O-5004", "C-101", "delivered", 1),  # the shop API times out on this one
]
LINES = [  # order, description, kind, cents
    ("O-5001", "Blue kite", "item", 2000),
    ("O-5002", "Kite string", "item", 2000),
    ("O-5002", "Lifetime spend", "note", 200000),  # a note, not something sold
    ("O-5003", "Stunt kite", "item", 4500),
    ("O-5004", "Kite tail", "item", 1500),
]

TABLES = """
create table customers (id text primary key, name text, email text,
                        address text, status text default 'open');
create table orders (id text primary key, customer_id text, status text,
                     api_times_out integer);
create table order_lines (order_id text, description text, kind text,
                          cents integer);
create table refunds (order_id text, cents integer, run_id text);
create table changes (seq integer primary key, run_id text, kind text,
                      target text, detail text);
create table counters (name text primary key, value integer);
"""


class ShopTimeout(Exception):
    """The shop API did not answer in time."""


def state_dir() -> Path:
    return Path(os.environ.get("BLUEKITE_HOME", ".")) / "state"


def connect() -> sqlite3.Connection:
    path = state_dir() / "shop.db"
    if not path.exists():
        reset()
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


def reset() -> None:
    """Delete all state and load the starting shop data."""
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        old.unlink()
    db = sqlite3.connect(folder / "shop.db")
    db.executescript(TABLES)
    db.executemany("insert into customers values (?,?,?,?,'open')", CUSTOMERS)
    db.executemany("insert into orders values (?,?,?,?)", ORDERS)
    db.executemany("insert into order_lines values (?,?,?,?)", LINES)
    db.commit()
    db.close()


def next_id(db: sqlite3.Connection, name: str) -> int:
    """A counter in the database: run ids are r-0001, r-0002, ... after a reset."""
    db.execute("insert or ignore into counters values (?, 0)", (name,))
    db.execute("update counters set value = value + 1 where name = ?", (name,))
    db.commit()
    row = db.execute("select value from counters where name = ?", (name,))
    return row.fetchone()[0]


def record_change(db, run_id: str, kind: str, target: str, detail: str) -> None:
    db.execute(
        "insert into changes (run_id, kind, target, detail) values (?,?,?,?)",
        (run_id, kind, target, detail),
    )
    db.commit()


def list_changes(db) -> list[sqlite3.Row]:
    return db.execute("select * from changes order by seq").fetchall()


def get_customer(db, customer_id: str) -> dict | None:
    row = db.execute("select * from customers where id = ?", (customer_id,))
    found = row.fetchone()
    return dict(found) if found else None


def first_customer_named(db, name: str) -> dict | None:
    row = db.execute("select * from customers where name = ? order by id", (name,))
    found = row.fetchone()
    return dict(found) if found else None


def get_order(db, order_id: str) -> dict | None:
    row = db.execute("select * from orders where id = ?", (order_id,)).fetchone()
    if row is None:
        return None
    order = dict(row)
    lines = db.execute(
        "select description, kind, cents from order_lines where order_id = ?",
        (order_id,),
    )
    order["lines"] = [dict(line) for line in lines]
    return order


def refunded_cents(db, order_id: str) -> int:
    row = db.execute(
        "select coalesce(sum(cents), 0) from refunds where order_id = ?", (order_id,)
    )
    return row.fetchone()[0]


def list_refunds(db) -> list[tuple[str, int]]:
    rows = db.execute("select order_id, cents from refunds")
    return [(row["order_id"], row["cents"]) for row in rows]


def refund(db, order_id: str, cents: int, run_id: str) -> None:
    order = get_order(db, order_id)
    if order["api_times_out"]:
        raise ShopTimeout("shop api timed out after 5s")
    db.execute("insert into refunds values (?,?,?)", (order_id, cents, run_id))
    db.commit()


def close(db, customer_id: str) -> None:
    db.execute("update customers set status = 'closed' where id = ?", (customer_id,))
    db.commit()


def set_address(db, customer_id: str, address: str) -> None:
    db.execute(
        "update customers set address = ? where id = ?", (address, customer_id)
    )
    db.commit()
