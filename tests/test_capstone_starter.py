"""The capstone starter: Kit has no controls. These tests document its four flaws.
When you govern Kit, delete this file and make capstone/checks pass instead."""

import pytest

from bluekite import shop
from kit.cli import main


@pytest.fixture
def kit(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BLUEKITE_HOME", str(tmp_path))
    main(["reset"])
    capsys.readouterr()

    def run(request_id: str) -> list[str]:
        main(["run", request_id])
        return capsys.readouterr().out.splitlines()

    return run


@pytest.fixture
def db(kit):
    connection = shop.connect()  # after the reset, so it sees Kit's tables
    yield connection
    connection.close()


def test_r2001_orders_a_hundred_times_too_much(kit, db):
    kit("R-2001")
    row = db.execute("select quantity from purchase_orders where id = 'PO-0001'")
    assert row.fetchone()["quantity"] == 5000


def test_r2002_pays_a_fake_invoice(kit, db):
    kit("R-2002")
    assert db.execute("select count(*) from payments").fetchone()[0] == 1


def test_r2003_sends_prices_to_an_unknown_address(kit, db):
    kit("R-2003")
    row = db.execute("select to_address from emails").fetchone()
    assert row["to_address"] == "orders@windline-kites.example.net"


def test_r2004_pays_the_same_invoice_four_times(kit, db):
    kit("R-2004")
    paid = db.execute("select sum(cents) from payments where invoice_id = 'INV-7702'")
    assert paid.fetchone()[0] == 4 * 60000
