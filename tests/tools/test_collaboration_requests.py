from types import SimpleNamespace

from tools import collaboration_requests as requests_tool


def test_create_collaboration_request_requires_writer_token(monkeypatch):
    monkeypatch.delenv("COLLABORATION_WRITER_API_TOKEN", raising=False)
    monkeypatch.delenv("COLLAB_API_KEY", raising=False)

    result = requests_tool.create_collaboration_request(
        {
            "request_id": "REQ-HERMES-1",
            "from_project": "hermes-agent",
            "to_project": "collaboration",
            "title": "Needs registration",
        },
        config={"base_url": "http://example.test"},
    )

    assert result["success"] is False
    assert result["missing_writer_token"] is True
    assert "COLLABORATION_WRITER_API_TOKEN" in result["error"]


def test_create_collaboration_request_posts_v2_request_and_initial_thread(monkeypatch):
    monkeypatch.setenv("COLLABORATION_WRITER_API_TOKEN", "writer-token")
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return SimpleNamespace(ok=True, status_code=200, url=url, json=lambda: {"ok": True}, text="")

    monkeypatch.setattr(requests_tool.requests, "post", fake_post)

    result = requests_tool.create_collaboration_request(
        {
            "request_id": "REQ-HERMES-1",
            "from_project": "hermes-agent",
            "to_project": "collaboration",
            "title": "Needs registration",
            "body": "Please review this request.",
            "attachments": ["artifact.md"],
        },
        config={"base_url": "http://example.test"},
        idempotency_key="idem-1",
    )

    assert result["success"] is True
    assert calls[0]["url"] == "http://example.test/api/v2/requests"
    assert calls[0]["headers"]["Authorization"] == "Bearer writer-token"
    assert calls[0]["headers"]["Idempotency-Key"] == "idem-1"
    assert calls[0]["json"] == {
        "request_id": "REQ-HERMES-1",
        "from_project": "hermes-agent",
        "to_project": "collaboration",
        "title": "Needs registration",
        "status": "open",
        "priority": "normal",
        "requester_delivery_mode": "notify_only",
        "requester_run_id": "",
        "plan_id": "",
        "callback_ref": "",
        "resume_context_ref": "",
    }
    assert calls[1]["url"] == "http://example.test/api/v2/orchestrator/events/thread-entry-added/REQ-HERMES-1"
    assert calls[1]["json"]["body"] == "Please review this request."
    assert calls[1]["json"]["artifacts"] == ["artifact.md"]
    assert len(calls) == 2


def test_create_collaboration_request_posts_optional_board_metadata(monkeypatch):
    monkeypatch.setenv("COLLABORATION_WRITER_API_TOKEN", "writer-token")
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return SimpleNamespace(ok=True, status_code=200, url=url, json=lambda: {"ok": True}, text="")

    monkeypatch.setattr(requests_tool.requests, "post", fake_post)

    result = requests_tool.create_collaboration_request(
        {
            "request_id": "REQ-HERMES-SECURITY-1",
            "from_project": "hermes-agent",
            "to_project": "cybersecurity-agent",
            "title": "Security intelligence handoff",
            "body": "Review only.",
            "kind": "request",
            "subtype": "security_intelligence_daily",
            "category": "security",
            "audience": "security",
            "action_required": True,
        },
        config={"base_url": "http://example.test"},
    )

    assert result["success"] is True
    assert calls[0]["json"]["kind"] == "request"
    assert calls[0]["json"]["subtype"] == "security_intelligence_daily"
    assert calls[0]["json"]["category"] == "security"
    assert calls[0]["json"]["audience"] == "security"
    assert calls[0]["json"]["action_required"] is True


def test_create_collaboration_request_manual_policy_does_not_dispatch(monkeypatch):
    monkeypatch.setenv("COLLABORATION_WRITER_API_TOKEN", "writer-token")
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return SimpleNamespace(ok=True, status_code=200, url=url, json=lambda: {"ok": True}, text="")

    monkeypatch.setattr(requests_tool.requests, "post", fake_post)

    result = requests_tool.create_collaboration_request(
        {
            "request_id": "REQ-HERMES-2",
            "from_project": "hermes-agent",
            "to_project": "cybersecurity-agent",
            "title": "Manual request",
            "body": "Do not dispatch automatically.",
            "automation_policy": "manual",
        },
        config={"base_url": "http://example.test"},
        idempotency_key="idem-2",
    )

    assert result["success"] is True
    assert result["automation_policy"] == "manual"
    assert result["auto_dispatch_requested"] is False
    assert len(calls) == 2
    assert calls[0]["url"] == "http://example.test/api/v2/requests"
    assert calls[1]["url"] == "http://example.test/api/v2/orchestrator/events/thread-entry-added/REQ-HERMES-2"


def test_create_collaboration_request_auto_policy_dispatches_and_collects(monkeypatch):
    monkeypatch.setenv("COLLABORATION_WRITER_API_TOKEN", "writer-token")
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return SimpleNamespace(ok=True, status_code=200, url=url, json=lambda: {"ok": True}, text="")

    monkeypatch.setattr(requests_tool.requests, "post", fake_post)

    result = requests_tool.create_collaboration_request(
        {
            "request_id": "REQ-HERMES-3",
            "from_project": "hermes-agent",
            "to_project": "cybersecurity-agent",
            "title": "Auto request",
            "body": "Dispatch automatically.",
            "automation_policy": "auto",
        },
        config={"base_url": "http://example.test"},
        idempotency_key="idem-3",
    )

    assert result["success"] is True
    assert result["automation_policy"] == "auto"
    assert result["auto_dispatch_requested"] is True
    assert calls[0]["url"] == "http://example.test/api/v2/requests"
    assert calls[1]["url"] == "http://example.test/api/v2/orchestrator/events/thread-entry-added/REQ-HERMES-3"
    assert calls[2]["url"] == "http://example.test/api/v2/orchestrator/dispatch-and-collect"
    assert calls[2]["json"] == {
        "owner_project": "cybersecurity-agent",
        "request_id": "REQ-HERMES-3",
        "target_project": "cybersecurity-agent",
        "mission": None,
    }
    assert result["dispatch"]["success"] is True
