from types import SimpleNamespace

import pytest

from tools import collaboration_responses as responses


def test_draft_collaboration_response_writes_local_draft(tmp_path):
    config = {"response_outbox_path": str(tmp_path / "outbox.json")}

    result = responses.draft_collaboration_response("REQ-1", "Looks good", config=config)

    assert result["success"] is True
    draft = result["draft"]
    assert draft["action_id"]
    assert draft["request_id"] == "REQ-1"
    assert draft["body"] == "Looks good"
    assert draft["status"] == "draft"
    assert (tmp_path / "outbox.json").exists()


def test_draft_collaboration_response_rejects_empty_request_id(tmp_path):
    config = {"response_outbox_path": str(tmp_path / "outbox.json")}

    result = responses.draft_collaboration_response("", "Looks good", config=config)

    assert result["success"] is False
    assert "request_id" in result["error"]


def test_draft_collaboration_response_rejects_empty_body(tmp_path):
    config = {"response_outbox_path": str(tmp_path / "outbox.json")}

    result = responses.draft_collaboration_response("REQ-1", "   ", config=config)

    assert result["success"] is False
    assert "body" in result["error"]


def test_list_collaboration_response_drafts_returns_newest_first(tmp_path, monkeypatch):
    config = {"response_outbox_path": str(tmp_path / "outbox.json")}
    times = iter(["2026-05-08T00:00:00Z", "2026-05-08T00:01:00Z"])
    monkeypatch.setattr(responses, "_utc_now", lambda: next(times))

    first = responses.draft_collaboration_response("REQ-1", "First", config=config)
    second = responses.draft_collaboration_response("REQ-2", "Second", config=config)
    result = responses.list_collaboration_response_drafts(config=config)

    assert result["success"] is True
    assert [draft["action_id"] for draft in result["drafts"]] == [second["action_id"], first["action_id"]]


def test_post_collaboration_response_posts_once_and_marks_posted(tmp_path, monkeypatch):
    config = {"response_outbox_path": str(tmp_path / "outbox.json"), "base_url": "http://example.test"}
    draft = responses.draft_collaboration_response("REQ-1", "Looks good", config=config)["draft"]
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return SimpleNamespace(ok=True, status_code=200, url=url, json=lambda: {"ok": True}, text="")

    monkeypatch.setattr(responses.requests, "post", fake_post)

    result = responses.post_collaboration_response(draft["action_id"], config=config)
    again = responses.post_collaboration_response(draft["action_id"], config=config)

    assert result["success"] is True
    assert result["draft"]["status"] == "posted"
    assert calls == [
        {
            "url": "http://example.test/api/v1/board/items/REQ-1/respond",
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Idempotency-Key": draft["action_id"],
            },
            "json": {"body": "Looks good", "client_msg_id": draft["action_id"]},
            "timeout": responses.WRITE_TIMEOUT_SECONDS,
        }
    ]
    assert again["success"] is False
    assert "already posted" in again["error"]


def test_post_collaboration_response_failed_api_remains_retryable(tmp_path, monkeypatch):
    config = {"response_outbox_path": str(tmp_path / "outbox.json"), "base_url": "http://example.test"}
    draft = responses.draft_collaboration_response("REQ-1", "Looks good", config=config)["draft"]

    def fake_post(url, headers, json, timeout):
        return SimpleNamespace(ok=False, status_code=500, url=url, json=lambda: {"error": "boom"}, text="boom")

    monkeypatch.setattr(responses.requests, "post", fake_post)

    result = responses.post_collaboration_response(draft["action_id"], config=config)

    assert result["success"] is False
    assert result["draft"]["status"] == "failed"
    assert result["draft"]["last_status_code"] == 500


def test_post_collaboration_response_refuses_missing_action_id(tmp_path):
    config = {"response_outbox_path": str(tmp_path / "outbox.json")}

    result = responses.post_collaboration_response("missing", config=config)

    assert result["success"] is False
    assert "No collaboration response draft" in result["error"]


def test_post_collaboration_response_records_request_exception(tmp_path, monkeypatch):
    config = {"response_outbox_path": str(tmp_path / "outbox.json"), "base_url": "http://example.test"}
    draft = responses.draft_collaboration_response("REQ-1", "Looks good", config=config)["draft"]

    def fake_post(url, headers, json, timeout):
        raise responses.requests.Timeout("slow")

    monkeypatch.setattr(responses.requests, "post", fake_post)

    result = responses.post_collaboration_response(draft["action_id"], config=config)

    assert result["success"] is False
    assert result["draft"]["status"] == "failed"
    assert "Timeout" in result["error"]
