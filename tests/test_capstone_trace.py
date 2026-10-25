"""Kit's trace starts the same way in the starter and in the solution."""

from kit.cli import main


def test_the_trace_names_the_request(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BLUEKITE_HOME", str(tmp_path))
    main(["reset"])
    main(["run", "R-2001"])
    lines = capsys.readouterr().out.splitlines()
    assert lines[1].startswith("request R-2001 · agent kit · run r-0001")
