from bluekite import shop
from bluekite.money import dollars, to_cents


def test_reset_loads_the_shop(db):
    assert shop.get_customer(db, "C-101")["name"] == "Anna Silva"
    assert len(shop.get_order(db, "O-5002")["lines"]) == 2
    assert shop.list_changes(db) == []


def test_two_customers_share_a_name(db):
    rows = db.execute("select id from customers where name = 'David Lee'")
    assert [row["id"] for row in rows] == ["C-102", "C-103"]


def test_run_ids_count_from_one_after_reset(db):
    assert shop.next_id(db, "run") == 1
    assert shop.next_id(db, "run") == 2


def test_money():
    assert to_cents(2000.00) == 200000
    assert dollars(200000) == "$2,000.00"
