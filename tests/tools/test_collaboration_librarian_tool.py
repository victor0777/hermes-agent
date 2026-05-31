import json
from pathlib import Path
from unittest.mock import Mock

from tools.collaboration_librarian_tool import (
    collaboration_librarian_digest_tool,
    generate_collaboration_librarian_digest,
)


def _response(url, payload):
    response = Mock()
    response.ok = True
    response.status_code = 200
    response.url = url
    response.json.return_value = payload
    return response


def test_librarian_digest_writes_json_and_markdown_with_request_ids(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/api/v1/dashboard"):
            return _response(url, {"projects": [{"project": "hermes-agent"}]})
        if url.endswith("/api/v2/inbox/hermes-agent"):
            return _response(url, {"items": []})
        if url.endswith("/api/v2/inbox/all"):
            return _response(
                url,
                {
                    "items": [
                        {
                            "request_id": "REQ-20260530-104",
                            "title": "Confirm portal contract",
                            "from_project": "enterprise-customer-portal",
                            "to_project": "hermes-agent",
                            "status": "delivered",
                            "priority": "normal",
                            "waiting_on": "requester",
                            "action": "close_or_reply",
                            "next_action": "review_result_and_decide_close_reply_or_escalate",
                            "updated_at": "2026-05-29T23:31:52Z",
                            "last_entry_id": "resp-1",
                        },
                        {
                            "request_id": "REQ-20260520-001",
                            "title": "Old item outside lookback",
                            "from_project": "old",
                            "to_project": "hermes-agent",
                            "status": "closed",
                            "updated_at": "2026-05-01T00:00:00Z",
                        },
                    ]
                },
            )
        if url.endswith("/api/v2/orchestrator/activation-logs"):
            assert kwargs["params"]["request_id"] == "REQ-20260530-104"
            return _response(
                url,
                {
                    "items": [
                        {
                            "event_id": "trace-REQ-20260530-104-msg-001",
                            "event_type": "request_created",
                            "context_summary": "Requester asked for endpoint details and freshness metadata.",
                            "metadata": {"entry_id": "msg-001"},
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(url, **kwargs):
        assert url == "http://192.168.0.199/v1/chat/completions"
        body = kwargs["json"]
        assert body["model"] == "qwen36-35b"
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        assert body["response_format"] == {"type": "json_object"}
        assert "REQ-20260530-104" in body["messages"][1]["content"]
        return _response(
            url,
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "project_topics": [
                                        {
                                            "project_id": "hermes-agent",
                                            "topic": "Portal contract follow-up",
                                            "request_ids": ["REQ-20260530-104"],
                                            "source_refs": ["collaboration:v2:request:REQ-20260530-104"],
                                        }
                                    ],
                                    "decisions": [
                                        {
                                            "project_id": "hermes-agent",
                                            "summary": "A delivered request needs requester review.",
                                            "request_ids": ["REQ-20260530-104"],
                                            "source_refs": ["collaboration:v2:request:REQ-20260530-104"],
                                        }
                                    ],
                                    "open_questions": [
                                        {
                                            "project_id": "hermes-agent",
                                            "question": "Should the requester close or reply?",
                                            "request_ids": ["REQ-20260530-104"],
                                            "source_refs": ["collaboration:v2:request:REQ-20260530-104"],
                                        }
                                    ],
                                    "next_actions": [
                                        {
                                            "project_id": "hermes-agent",
                                            "action": "Review result and decide close/reply/escalate.",
                                            "request_ids": ["REQ-20260530-104"],
                                            "source_refs": ["collaboration:v2:request:REQ-20260530-104"],
                                        }
                                    ],
                                    "related_request_groups": [
                                        {
                                            "theme": "Portal readiness",
                                            "request_ids": ["REQ-20260530-104"],
                                            "source_refs": ["collaboration:v2:request:REQ-20260530-104"],
                                            "reason": "Single request defines the current thread.",
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("tools.collaboration_librarian_tool.requests.get", fake_get)
    monkeypatch.setattr("tools.collaboration_librarian_tool.requests.post", fake_post)

    result = generate_collaboration_librarian_digest(
        days=7,
        projects="all",
        output_dir=str(tmp_path),
        config={"base_url": "http://collab.test"},
    )

    assert result["success"] is True
    assert result["item_count"] == 1
    assert result["request_ids"] == ["REQ-20260530-104"]
    assert result["validation"]["missing_request_ids"] == []
    assert result["validation"]["shared_state_write_attempted"] is False
    assert len(calls) == 4

    index = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
    assert index["shared_state_write_attempted"] is False
    assert index["llm"]["model"] == "qwen36-35b"
    assert index["llm"]["base_url"] == "http://192.168.0.199/v1"
    assert index["llm"]["enabled"] is True
    assert index["llm_summary"]["success"] is True
    assert index["llm_summary"]["project_topics"][0]["request_ids"] == ["REQ-20260530-104"]
    assert index["items"][0]["request_id"] == "REQ-20260530-104"
    assert index["items"][0]["thread_snippets"][0]["entry_id"] == "msg-001"
    assert "`REQ-20260530-104`" in markdown
    assert "collaboration:v2:request:REQ-20260530-104" in markdown
    assert "## Librarian Summary" in markdown
    assert "### Related Request Groups" in markdown


def test_librarian_digest_tool_can_render_without_writing(tmp_path, monkeypatch):
    def fake_get(url, **kwargs):
        if url.endswith("/api/v1/dashboard"):
            return _response(url, {"projects": [{"project": "hermes-agent"}]})
        return _response(url, {"items": []})

    monkeypatch.setattr("tools.collaboration_librarian_tool.requests.get", fake_get)

    result = json.loads(
        collaboration_librarian_digest_tool(
            days=7,
            projects="all",
            write_draft=False,
            output_dir=str(tmp_path),
            include_thread_snippets=False,
            use_llm_summary=False,
        )
    )

    assert result["status"] == "draft_rendered"
    assert result["json_path"] == ""
    assert result["markdown_path"] == ""
    assert result["validation"]["item_count"] == 0
    assert not list(tmp_path.glob("knowledge-*"))
