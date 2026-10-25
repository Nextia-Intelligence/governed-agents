from bluekite.governance import audit, metrics


def test_metrics_count_what_the_controls_did(replay):
    for ticket_id in ("T-1001", "T-1002", "T-1003", "T-1004", "T-1005"):
        replay(ticket_id)
    m = metrics.summarize(audit.read_events())
    assert m["runs"] == {"done": 3, "paused": 1, "stopped": 1}
    assert sum(m["denials"].values()) == 3
    assert m["asked"] == 1
    assert m["stops"] == {"loop": 1}
    assert m["flags"] == 1
