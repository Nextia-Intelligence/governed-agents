"""The bluekite command, end to end, as the videos show it."""

from bluekite.cli import main


def output(capsys, *argv: str) -> list[str]:
    main(list(argv))
    return capsys.readouterr().out.splitlines()


def test_ticket_lines_fit_the_screen(db, capsys):
    lines = output(capsys, "tickets")
    assert len(lines) == 5
    assert all(len(line) <= 88 for line in lines)
    assert lines[0].startswith("T-1001  david.lee@example.com")


def test_check_explain_shows_the_facts_and_the_cedar_request(db, capsys):
    lines = output(capsys, "check", "issue_refund", "order_id=O-5002",
                   "amount=2000", "--for", "C-102", "--explain")
    assert "facts the guard gathered" in lines
    assert "  refundable_cents  2000" in lines  # read from the shop
    assert '  resource   Order::"O-5002"' in lines
    assert '    owner = Customer::"C-102"' in lines
    assert all(len(line) <= 88 for line in lines)
