import json
from types import SimpleNamespace

from tools import collaboration_responses as responses
from tools.collaboration_monitor import (
    SILENT_MARKER,
    build_daily_brief,
    build_pm_digest,
    detect_inbound_requests,
    evaluate_urgent_alerts,
    read_inbound_inbox,
    run_monitor,
)


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

    def test_inbound_monitor_reports_first_seen_open_requests(self, monkeypatch, tmp_path):
        state_path = tmp_path / "seen.json"
        inbox_path = tmp_path / "inbox.json"

        def fake_tool(**kwargs):
            assert kwargs == {"action": "list_requests", "project": "hermes-agent", "status": "open", "limit": 7}
            return _payload(data=[{"request_id": "REQ-1", "title": "Needs review", "priority": "medium"}])

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = detect_inbound_requests(
            limit=7,
            project="hermes-agent",
            config={"inbound_state_path": str(state_path), "inbound_inbox_path": str(inbox_path)},
        )

        assert result["success"] is True
        assert result["should_notify"] is True
        assert result["counts"] == {"new": 1, "open": 1, "seen": 1, "pending": 1}
        assert result["new_items"][0]["_inbound_id"] == "REQ-1"
        assert "Needs review" in result["text"]
        assert "REQ-1" in state_path.read_text()
        inbox = json.loads(inbox_path.read_text())
        assert inbox["items"]["REQ-1"]["status"] == "pending"
        assert inbox["items"]["REQ-1"]["title"] == "Needs review"

    def test_inbound_monitor_suppresses_duplicate_requests(self, monkeypatch, tmp_path):
        state_path = tmp_path / "seen.json"
        inbox_path = tmp_path / "inbox.json"

        def fake_tool(**kwargs):
            return _payload(data=[{"request_id": "REQ-1", "title": "Needs review"}])

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)
        config = {"inbound_state_path": str(state_path), "inbound_inbox_path": str(inbox_path)}

        first = detect_inbound_requests(config=config)
        second = detect_inbound_requests(config=config)

        assert first["should_notify"] is True
        assert second["success"] is True
        assert second["should_notify"] is False
        assert second["text"] == SILENT_MARKER
        assert second["counts"] == {"new": 0, "open": 1, "seen": 1, "pending": 1}
        assert list(json.loads(inbox_path.read_text())["items"]) == ["REQ-1"]

    def test_inbound_monitor_reports_only_new_request(self, monkeypatch, tmp_path):
        state_path = tmp_path / "seen.json"
        inbox_path = tmp_path / "inbox.json"
        state_path.write_text('{"version": 1, "seen": {"REQ-1": {"first_seen_at": "2026-05-08T00:00:00Z"}}}')

        def fake_tool(**kwargs):
            return _payload(data=[
                {"request_id": "REQ-1", "title": "Old request"},
                {"request_id": "REQ-2", "title": "New request", "priority": "high"},
            ])

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = detect_inbound_requests(config={"inbound_state_path": str(state_path), "inbound_inbox_path": str(inbox_path)})

        assert result["should_notify"] is True
        assert [item["_inbound_id"] for item in result["new_items"]] == ["REQ-2"]
        assert "New request" in result["text"]
        assert "Old request" not in result["text"]
        assert set(json.loads(inbox_path.read_text())["items"]) == {"REQ-1", "REQ-2"}

    def test_inbound_monitor_api_failure_does_not_write_state(self, monkeypatch, tmp_path):
        state_path = tmp_path / "seen.json"
        inbox_path = tmp_path / "inbox.json"

        def fake_tool(**kwargs):
            return _payload(success=False, error="HTTP 500")

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = detect_inbound_requests(config={"inbound_state_path": str(state_path), "inbound_inbox_path": str(inbox_path)})

        assert result["success"] is False
        assert "HTTP 500" in result["text"]
        assert not state_path.exists()
        assert not inbox_path.exists()

    def test_inbound_monitor_preview_does_not_write_state(self, monkeypatch, tmp_path):
        state_path = tmp_path / "seen.json"
        inbox_path = tmp_path / "inbox.json"

        def fake_tool(**kwargs):
            return _payload(data=[{"request_id": "REQ-1", "title": "Preview request"}])

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = detect_inbound_requests(
            config={"inbound_state_path": str(state_path), "inbound_inbox_path": str(inbox_path)},
            mark_seen=False,
        )

        assert result["success"] is True
        assert result["should_notify"] is True
        assert result["counts"] == {"new": 1, "open": 1, "seen": 0, "pending": 0}
        assert not state_path.exists()
        assert not inbox_path.exists()

    def test_pm_digest_filters_related_items_and_counts_signals(self, monkeypatch):
        calls = []

        def fake_tool(**kwargs):
            calls.append(kwargs)
            if kwargs["action"] == "list_requests":
                return _payload(data=[
                    {"request_id": "REQ-1", "from_project": "llm-gateway", "to_project": "llm-routing-telemetry", "title": "Telemetry needed", "priority": "high", "age_days": 4},
                    {"request_id": "REQ-2", "from_project": "unrelated", "to_project": "other", "title": "Ignore this", "priority": "high", "age_days": 9},
                    {"request_id": "REQ-3", "from_project": "agents", "to_project": "auto_researcher", "title": "llm-routing-telemetry continuation", "updated_age_days": 2},
                ])
            if kwargs["action"] == "overdue_requests":
                return _payload(data=[
                    {"request_id": "REQ-4", "from_project": "llm-gateway", "to_project": "auto_researcher", "title": "Overdue continuation"},
                    {"request_id": "REQ-5", "from_project": "other", "title": "Unrelated overdue"},
                ])
            if kwargs["action"] == "blockers":
                return _payload(data=[{"request_id": "REQ-6", "body": "llm-routing-telemetry blocker"}])
            if kwargs["action"] == "project_summary":
                return _payload(data={"phase": f"{kwargs['project']} phase", "blocker_count": 0})
            raise AssertionError(kwargs)

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = build_pm_digest(["llm-gateway", "llm-routing-telemetry"], limit=9)

        assert result["success"] is True
        assert result["kind"] == "pm_digest"
        assert result["counts"] == {"open": 2, "high_priority": 1, "overdue": 1, "blockers": 1, "stale": 2, "project_summaries_failed": 0}
        assert result["severity"] == "high"
        assert "Telemetry needed" in result["text"]
        assert "llm-routing-telemetry continuation" in result["text"]
        assert "Ignore this" not in result["text"]
        assert calls[0] == {"action": "list_requests", "status": "open", "limit": 9}
        assert {call["action"] for call in calls} == {"list_requests", "overdue_requests", "blockers", "project_summary"}

    def test_pm_digest_stale_requires_explicit_age_fields(self, monkeypatch):
        def fake_tool(**kwargs):
            if kwargs["action"] == "list_requests":
                return _payload(data=[{"request_id": "REQ-1", "from_project": "llm-gateway", "title": "Old-looking title"}])
            if kwargs["action"] in {"overdue_requests", "blockers"}:
                return _payload(data=[])
            if kwargs["action"] == "project_summary":
                return _payload(data={"phase": "ok"})
            raise AssertionError(kwargs)

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = build_pm_digest(["llm-gateway"])

        assert result["counts"]["open"] == 1
        assert result["counts"]["stale"] == 0
        assert result["severity"] == "info"

    def test_pm_digest_partial_failures_include_warning_text(self, monkeypatch):
        def fake_tool(**kwargs):
            if kwargs["action"] == "list_requests":
                return _payload(data=[{"request_id": "REQ-1", "from_project": "llm-gateway", "title": "Open item"}])
            if kwargs["action"] == "overdue_requests":
                return _payload(success=False, error="HTTP 500")
            if kwargs["action"] == "blockers":
                return _payload(data=[])
            if kwargs["action"] == "project_summary":
                return _payload(success=False, error="summary down")
            raise AssertionError(kwargs)

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        result = build_pm_digest(["llm-gateway"])

        assert result["success"] is False
        assert result["severity"] == "error"
        assert result["counts"]["open"] == 1
        assert result["counts"]["project_summaries_failed"] == 1
        assert "HTTP 500" in result["text"]
        assert "summary down" in result["text"]
        assert "Safety: read-only digest" in result["text"]

    def test_run_monitor_dispatches_inbound_requests(self, monkeypatch, tmp_path):
        state_path = tmp_path / "seen.json"
        inbox_path = tmp_path / "inbox.json"

        def fake_tool(**kwargs):
            return _payload(data=[{"request_id": "REQ-1", "title": "Inbound"}])

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)

        evidence_path = tmp_path / "evidence.json"
        result = run_monitor(
            "inbound_requests",
            config={
                "inbound_state_path": str(state_path),
                "inbound_inbox_path": str(inbox_path),
                "autonomy_evidence_path": str(evidence_path),
            },
        )

        assert result["success"] is True
        assert result["kind"] == "inbound_requests"
        assert result["should_notify"] is True
        evidence = evidence_path.read_text()
        assert "monitor_run" in evidence
        assert "inbound_request_detected" in evidence
        assert "REQ-1" in evidence

    def test_read_inbound_inbox_returns_pending_items(self, tmp_path):
        inbox_path = tmp_path / "inbox.json"
        inbox_path.write_text(json.dumps({
            "version": 1,
            "items": {
                "REQ-1": {"id": "REQ-1", "request_id": "REQ-1", "title": "Pending review", "status": "pending", "last_seen_at": "2026-05-08T01:00:00Z"},
                "REQ-2": {"id": "REQ-2", "request_id": "REQ-2", "title": "Done", "status": "done", "last_seen_at": "2026-05-08T02:00:00Z"},
            },
        }))

        result = read_inbound_inbox(config={"inbound_inbox_path": str(inbox_path)})

        assert result["success"] is True
        assert result["counts"] == {"pending": 1}
        assert [item["id"] for item in result["items"]] == ["REQ-1"]
        assert "Pending review" in result["text"]

    def test_read_inbound_inbox_returns_empty_message(self, tmp_path):
        result = read_inbound_inbox(config={"inbound_inbox_path": str(tmp_path / "missing.json")})

        assert result["success"] is True
        assert result["items"] == []
        assert "No pending inbound" in result["text"]

    def test_inbound_to_approved_response_smoke_flow(self, monkeypatch, tmp_path):
        state_path = tmp_path / "seen.json"
        inbox_path = tmp_path / "inbox.json"
        outbox_path = tmp_path / "outbox.json"
        calls = []

        def fake_tool(**kwargs):
            return _payload(data=[{"request_id": "REQ-1", "title": "Needs response", "priority": "medium"}])

        def fake_post(url, headers, json, timeout):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
            return SimpleNamespace(ok=True, status_code=200, url=url, json=lambda: {"ok": True}, text="")

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)
        monkeypatch.setattr(responses.requests, "post", fake_post)
        monitor_config = {"inbound_state_path": str(state_path), "inbound_inbox_path": str(inbox_path)}
        response_config = {"response_outbox_path": str(outbox_path), "base_url": "http://example.test"}

        detected = detect_inbound_requests(project="hermes-agent", config=monitor_config)
        inbox = read_inbound_inbox(config=monitor_config)
        draft = responses.draft_collaboration_response(inbox["items"][0]["request_id"], "Response ready", config=response_config)
        posted = responses.post_collaboration_response(draft["action_id"], config=response_config)

        assert detected["should_notify"] is True
        assert inbox["items"][0]["request_id"] == "REQ-1"
        assert draft["draft"]["status"] == "draft"
        assert posted["success"] is True
        assert posted["draft"]["status"] == "posted"
        assert calls == [{
            "url": "http://example.test/api/v1/board/items/REQ-1/respond",
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Idempotency-Key": draft["action_id"],
            },
            "json": {"assignee": "hermes-agent", "body": "Response ready", "client_msg_id": draft["action_id"]},
            "timeout": responses.WRITE_TIMEOUT_SECONDS,
        }]

    def test_inbound_monitor_inbox_save_failure_returns_error(self, monkeypatch, tmp_path):
        state_path = tmp_path / "seen.json"
        inbox_path = tmp_path / "inbox.json"

        def fake_tool(**kwargs):
            return _payload(data=[{"request_id": "REQ-1", "title": "Cannot save"}])

        def fail_save(path, payload, **kwargs):
            if path == inbox_path:
                raise OSError("disk full")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)
        monkeypatch.setattr("tools.collaboration_monitor.atomic_json_write", fail_save)

        result = detect_inbound_requests(config={"inbound_state_path": str(state_path), "inbound_inbox_path": str(inbox_path)})

        assert result["success"] is False
        assert "local inbox" in result["text"]
        assert "disk full" in result["error"]
        assert result["counts"] == {"new": 1, "open": 1, "seen": 1, "pending": 1}

    def test_run_monitor_evidence_logging_failure_does_not_fail_result(self, monkeypatch):
        def fake_tool(**kwargs):
            return _payload(text="daily text")

        def fail_append(*args, **kwargs):
            raise OSError("cannot log")

        monkeypatch.setattr("tools.collaboration_monitor.collaboration_tool", fake_tool)
        monkeypatch.setattr("tools.collaboration_autonomy.append_evidence_event", fail_append)

        result = run_monitor("daily")

        assert result["success"] is True
        assert result["kind"] == "daily_brief"

    def test_unknown_monitor_kind_is_rejected(self):
        result = run_monitor("write_actions")

        assert result["success"] is False
        assert "Unsupported" in result["text"]
