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
