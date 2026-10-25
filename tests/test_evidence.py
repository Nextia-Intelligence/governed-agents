from pathlib import Path

from bluekite.governance import evidence

OFFICIAL = ("https://eur-lex.europa.eu/", "https://www.nist.gov/",
            "https://www.iso.org/", "https://genai.owasp.org/")


def test_the_pack_covers_every_control(replay):
    for ticket_id in ("T-1001", "T-1002", "T-1004", "T-1005"):
        replay(ticket_id)
    text, numbers = evidence.build(run_the_tests=False)
    for control in evidence.CONTROLS:
        assert control.name in text
    assert numbers["chain_ok"]
    assert text.count("**Sample audit event**") == 6


def test_framework_items_are_names_and_official_links_only():
    for short, name, link in evidence.FRAMEWORKS.values():
        assert link.startswith(OFFICIAL)
        assert len(name) < 90  # a name, not copied text


def test_the_pack_says_it_is_not_legal_advice():
    text, _ = evidence.build(run_the_tests=False)
    assert "This is not legal advice." in text


def test_every_file_in_the_pack_exists():
    for control in evidence.CONTROLS:
        for path in control.tests:
            assert (evidence.ROOT / path).exists(), path
        for ref in evidence.code_refs(control):
            assert Path(evidence.ROOT / ref.split("`")[1]).exists()


def test_no_empty_code_heading_and_nist_ai_600_1_is_named():
    text, _ = evidence.build(run_the_tests=False)
    assert text.count("**Code**") == sum(1 for c in evidence.CONTROLS if c.code)
    assert "**Code**\n\n**Tests**" not in text
    assert "NIST AI RMF 1.0, with its Generative AI Profile NIST AI 600-1" in text
