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


def test_variant_ids_never_touch_the_emails(db, capsys):
    lines = output(capsys, "tickets", "--variants")
    assert all(len(line) <= 88 for line in lines)
    for line in lines:
        ticket_id, rest = line.split(" ", 1)
        assert rest.startswith(" ")  # at least two spaces after every id


def test_reset_and_run(db, capsys):
    assert output(capsys, "reset")[0].startswith("reset:")
    lines = output(capsys, "run", "T-1001")
    assert lines[0] == "ticket T-1001 · agent sam · run r-0001 · for C-102"


def test_check(db, capsys):
    lines = output(capsys, "check", "issue_refund", "order_id=O-5002",
                   "amount=2000", "--for", "C-102")
    assert lines[1] == "python  deny · rule refund-within-order-total"
    assert lines[2] == "cedar   deny · rule refund-within-order-total"


def test_check_explain_shows_the_facts_and_the_cedar_request(db, capsys):
    lines = output(capsys, "check", "issue_refund", "order_id=O-5002",
                   "amount=2000", "--for", "C-102", "--explain")
    assert "facts the guard gathered" in lines
    assert "  refundable_cents  2000" in lines  # read from the shop
    assert '  resource   Order::"O-5002"' in lines
    assert '    owner = Customer::"C-102"' in lines
    assert all(len(line) <= 88 for line in lines)


def test_approve_and_resume(db, capsys):
    output(capsys, "run", "T-1002")
    assert output(capsys, "approvals")[0].startswith("A-0001  pending")
    output(capsys, "approve", "A-0001")
    lines = output(capsys, "resume", "r-0001")
    assert lines[-2].startswith("sam: Your account is closed.")


def test_check_explain_shows_the_args_hash(db, capsys):
    lines = output(capsys, "check", "close_account", "customer_id=C-103",
                   "--for", "C-103", "--explain")
    assert lines[-1].startswith("  sha256 a97cac6ee960")  # as in bluekite approvals
