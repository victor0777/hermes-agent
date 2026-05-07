import json

from tools.collaboration_monitor import SILENT_MARKER, build_daily_brief, evaluate_urgent_alerts, run_monitor


def _payload(success=True, data=None, text=None, error=None):
    result = {"success": success}
    if data is not None:
        result["data"] = data
    if text is not None:
        result["text"] = text
    if error is not None:
        result["error"] = error
    return json.dumps(result)


class TestCollaborationMonitor:
    def test_daily_brief_reuses_collaboration_brief(self, monkeypatch):
        calls = []

        def fake_tool(**kwargs):
            calls.append(kwargs)
            return _payload(text="daily text")

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = build_daily_brief(limit=7, project="hermes-agent")

        assert result["success"] is True
        assert result["kind"] == "daily_brief"
        assert result["should_notify"] is True
        assert result["text"] == "daily text"
        assert calls == [{"action": "brief", "project": "hermes-agent", "limit": 7}]

    def test_urgent_monitor_silent_when_no_items_exist(self, monkeypatch):
        def fake_tool(**kwargs):
            return _payload(data=[])

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = evaluate_urgent_alerts()

        assert result["success"] is True
        assert result["should_notify"] is False
        assert result["text"] == SILENT_MARKER
        assert result["counts"] == {"high_priority": 0, "overdue": 0, "blockers": 0}

    def test_urgent_monitor_alerts_on_high_priority_open_requests(self, monkeypatch):
        def fake_tool(**kwargs):
            if kwargs["action"] == "list_requests":
                return _payload(data=[{"request_id": "REQ-1", "title": "Needs decision", "priority": "high"}])
            return _payload(data=[])

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = evaluate_urgent_alerts()

        assert result["should_notify"] is True
        assert result["counts"]["high_priority"] == 1
        assert "Needs decision" in result["text"]

    def test_urgent_monitor_alerts_on_overdue_requests(self, monkeypatch):
        def fake_tool(**kwargs):
            if kwargs["action"] == "overdue_requests":
                return _payload(data=[{"request_id": "REQ-2", "title": "Overdue reply"}])
            return _payload(data=[])

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = evaluate_urgent_alerts()

        assert result["should_notify"] is True
        assert result["counts"]["overdue"] == 1
        assert "Overdue reply" in result["text"]

    def test_urgent_monitor_alerts_on_blockers(self, monkeypatch):
        def fake_tool(**kwargs):
            if kwargs["action"] == "blockers":
                return _payload(data=[{"title": "Dependency blocked"}])
            return _payload(data=[])

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = evaluate_urgent_alerts()

        assert result["should_notify"] is True
        assert result["counts"]["blockers"] == 1
        assert "Dependency blocked" in result["text"]

    def test_api_failure_returns_deliverable_error_text(self, monkeypatch):
        def fake_tool(**kwargs):
            if kwargs["action"] == "blockers":
                return _payload(success=False, error="HTTP 500")
            return _payload(data=[])

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = evaluate_urgent_alerts()

        assert result["success"] is False
        assert result["should_notify"] is True
        assert "HTTP 500" in result["text"]
        assert result["text"] != SILENT_MARKER

    def test_unknown_monitor_kind_is_rejected(self):
        result = run_monitor("write_actions")

        assert result["success"] is False
        assert "Unsupported" in result["text"]
