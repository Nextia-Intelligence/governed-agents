import pytest

from bluekite import shop_api
from bluekite.governance import credentials
from bluekite.governance.identity import identify
from bluekite.governance.registry import REGISTRY, validate


def test_identity_comes_from_the_sender_email(db):
    ticket = {"id": "T-1002", "from": "david.k.lee@example.com", "text": ""}
    assert identify(db, "sam", "r-0001", ticket).on_behalf_of == "C-103"


def test_an_unknown_sender_acts_for_nobody(db):
    ticket = {"id": "T-1003", "from": "anna.s.new@example.com", "text": ""}
    assert identify(db, "sam", "r-0001", ticket).on_behalf_of is None


@pytest.mark.parametrize("args, problem", [
    ({"order_id": "O-5002", "amount": 20.0}, None),
    ({"order_id": "5002", "amount": 20.0}, "does not match"),
    ({"order_id": "O-5002", "amount": -5.0}, "must be more than 0"),
    ({"order_id": "O-5002", "amount": "20"}, "must be a number"),
    ({"order_id": "O-5002", "amount": 9000.0}, "at most 5000"),
    ({"order_id": "O-5002"}, "missing amount"),
    ({"order_id": "O-5002", "amount": 20.0, "note": "x"}, "unknown argument"),
])
def test_refund_arguments_are_checked(args, problem):
    problems = validate(REGISTRY["issue_refund"], args)
    if problem is None:
        assert problems == []
    else:
        assert problem in problems[0]


def test_tools_take_ids_not_names():
    assert validate(REGISTRY["close_account"], {"customer_id": "David Lee"})


def test_a_read_token_cannot_refund(db):
    ticket = {"id": "T-1001", "from": "david.lee@example.com", "text": ""}
    me = identify(db, "sam", "r-0001", ticket)
    read_token = credentials.issue(me, REGISTRY["look_up_order"])
    with pytest.raises(credentials.ScopeError):
        shop_api.refund(db, read_token, "O-5002", 2000)


def test_every_tool_has_one_scope():
    scopes = [spec.scope for spec in REGISTRY.values()]
    assert len(set(scopes)) == len(scopes)
