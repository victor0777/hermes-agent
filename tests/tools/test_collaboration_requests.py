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
