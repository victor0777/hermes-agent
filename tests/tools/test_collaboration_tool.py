import json
from unittest.mock import Mock
from urllib.parse import urlencode

import requests

from tools.collaboration_tool import (
    collaboration_board_search,
    collaboration_search_knowledge,
    collaboration_tool,
    security_intelligence_intake_tool,
)


class TestCollaborationTool:
    def test_rejects_write_like_actions(self):
        result = json.loads(collaboration_tool(action="close_request"))

        assert result["success"] is False
        assert "read-only" in result["error"]

    def test_requires_project_for_project_summary(self):
        result = json.loads(collaboration_tool(action="project_summary"))

        assert result["success"] is False
        assert "project" in result["error"]

    def test_security_intelligence_intake_tool_reports_blocked_without_sources(self, monkeypatch):
        monkeypatch.setattr(
            "tools.collaboration_autonomy.collect_security_intelligence",
            lambda limit=100: {"success": False, "status": "blocked", "limit": limit},
        )

        result = json.loads(security_intelligence_intake_tool(limit=5))

        assert result == {"success": False, "status": "blocked", "limit": 5}

    def test_fetches_dashboard_with_default_base_url(self, monkeypatch):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.url = "http://collaboration.ktl.com/api/v1/dashboard?limit=20"
        response.json.return_value = {"ok": True}
        monkeypatch.setattr("tools.collaboration_tool.requests.get", Mock(return_value=response))

        result = json.loads(collaboration_tool(action="dashboard"))

        assert result["success"] is True
        assert result["data"] == {"ok": True}
        get = __import__("tools.collaboration_tool", fromlist=["requests"]).requests.get
        get.assert_called_once()
        assert get.call_args.args[0] == "http://collaboration.ktl.com/api/v1/dashboard"
        assert get.call_args.kwargs["headers"] == {"Accept": "application/json"}

    def test_uses_base_url_and_token_from_env(self, monkeypatch):
        monkeypatch.setenv("COLLABORATION_BASE_URL", "http://example.test")
        monkeypatch.setenv("COLLABORATION_API_TOKEN", "token-123")
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.url = "http://example.test/api/v1/requests"
        response.json.return_value = []
        mocked_get = Mock(return_value=response)
        monkeypatch.setattr("tools.collaboration_tool.requests.get", mocked_get)

        result = json.loads(collaboration_tool(action="list_requests", status="open", priority="high"))

        assert result["success"] is True
        assert mocked_get.call_args.args[0] == "http://example.test/api/v1/requests"
        assert mocked_get.call_args.kwargs["headers"]["Authorization"] == "Bearer token-123"
        assert mocked_get.call_args.kwargs["params"]["status"] == "open"
        assert mocked_get.call_args.kwargs["params"]["priority"] == "high"

    def test_returns_request_exception_as_json(self, monkeypatch):
        def fail(*args, **kwargs):
            raise requests.RequestException("boom")

        monkeypatch.setattr("tools.collaboration_tool.requests.get", fail)

        result = json.loads(collaboration_tool(action="dashboard"))

        assert result["success"] is False
        assert "boom" in result["error"]

    def test_brief_combines_read_only_sections(self, monkeypatch):
        responses = {
            "/api/v1/dashboard": {"ok": True},
            "/api/v1/requests": [
                {"title": "Fix blocked deploy", "priority": "high"},
                {"title": "Clean stale report", "priority": "medium"},
            ],
            "/api/v1/requests/overdue": [{"title": "Answer overdue request"}],
            "/api/v1/blockers": [{"title": "Dependency missing"}],
            "/api/v1/reports": [{"title": "map-par02 report"}],
        }

        def fake_get(url, **kwargs):
            response = Mock()
            response.ok = True
            response.status_code = 200
            response.url = url
            response.json.return_value = responses[url.replace("http://collaboration.ktl.com", "")]
            return response

        mocked_get = Mock(side_effect=fake_get)
        monkeypatch.setattr("tools.collaboration_tool.requests.get", mocked_get)

        result = json.loads(collaboration_tool(action="brief"))

        assert result["success"] is True
        assert result["action"] == "brief"
        assert "High-priority open requests" in result["text"]
        assert "Fix blocked deploy" in result["text"]
        assert "Answer overdue request" in result["text"]
        assert mocked_get.call_count == 5
        called_paths = [call.args[0].replace("http://collaboration.ktl.com", "") for call in mocked_get.call_args_list]
        assert called_paths == [
            "/api/v1/dashboard",
            "/api/v1/requests",
            "/api/v1/requests/overdue",
            "/api/v1/blockers",
            "/api/v1/reports",
        ]

    def test_brief_uses_dashboard_blockers_fallback(self, monkeypatch):
        responses = {
            "/api/v1/dashboard": {"blockers": [{"title": "Dashboard blocker"}]},
            "/api/v1/requests": [],
            "/api/v1/requests/overdue": [],
            "/api/v1/reports": [],
        }

        def fake_get(url, **kwargs):
            path = url.replace("http://collaboration.ktl.com", "")
            response = Mock()
            response.url = url
            if path == "/api/v1/blockers":
                response.ok = False
                response.status_code = 500
                response.text = "Internal Server Error"
                response.json.side_effect = ValueError("not json")
                return response
            response.ok = True
            response.status_code = 200
            response.json.return_value = responses[path]
            return response

        monkeypatch.setattr("tools.collaboration_tool.requests.get", Mock(side_effect=fake_get))

        result = json.loads(collaboration_tool(action="brief"))

        assert result["success"] is True
        assert "Dashboard blocker" in result["text"]
        assert "using dashboard blockers fallback" in result["text"]

    def test_search_knowledge_uses_api_base_and_preserves_snapshot_results(self, monkeypatch):
        monkeypatch.setenv("COLLABORATION_API_BASE", "http://api.example.test")
        monkeypatch.setenv("COLLABORATION_BASE_URL", "http://old.example.test")
        snapshot = {"id": "project-snapshot:OpenViking/README.md::0", "text": "context database"}

        def fake_get(url, **kwargs):
            response = Mock()
            response.ok = True
            response.status_code = 200
            response.url = f"{url}?{urlencode(kwargs['params'])}"
            response.json.return_value = {"results": [snapshot], "count": 1}
            return response

        mocked_get = Mock(side_effect=fake_get)
        monkeypatch.setattr("tools.collaboration_tool.requests.get", mocked_get)

        result = json.loads(collaboration_search_knowledge(
            query="OpenViking context database",
            project="OpenViking/a/b",
            limit=3,
        ))

        assert result["success"] is True
        assert result["results"] == [snapshot]
        assert result["data"]["results"] == [snapshot]
        assert result["count"] == 1
        assert mocked_get.call_args.args[0] == "http://api.example.test/api/v1/search/knowledge"
        assert "query=OpenViking+context+database" in result["url"]
        assert "project=OpenViking%2Fa%2Fb" in result["url"]

    def test_search_knowledge_falls_back_to_legacy_base_url(self, monkeypatch):
        monkeypatch.delenv("COLLABORATION_API_BASE", raising=False)
        monkeypatch.setenv("COLLABORATION_BASE_URL", "http://legacy.example.test")
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.url = "http://legacy.example.test/api/v1/search/knowledge?query=hermes"
        response.json.return_value = []
        mocked_get = Mock(return_value=response)
        monkeypatch.setattr("tools.collaboration_tool.requests.get", mocked_get)

        result = json.loads(collaboration_search_knowledge(query="hermes"))

        assert result["success"] is True
        assert mocked_get.call_args.args[0] == "http://legacy.example.test/api/v1/search/knowledge"

    def test_board_search_preserves_board_items(self, monkeypatch):
        board_item = {"id": "board-1", "category": "board_entry", "title": "reply needed"}

        def fake_get(url, **kwargs):
            response = Mock()
            response.ok = True
            response.status_code = 200
            response.url = f"{url}?{urlencode(kwargs['params'])}"
            response.json.return_value = {"items": [board_item], "count": 1}
            return response

        mocked_get = Mock(side_effect=fake_get)
        monkeypatch.setattr("tools.collaboration_tool.requests.get", mocked_get)

        result = json.loads(collaboration_board_search(q="reply", category="board_entry", limit=1))

        assert result["success"] is True
        assert result["items"] == [board_item]
        assert result["data"]["items"] == [board_item]
        assert result["count"] == 1
        assert mocked_get.call_args.args[0] == "http://collaboration.ktl.com/api/v1/board/search"
        assert mocked_get.call_args.kwargs["params"] == {"q": "reply", "category": "board_entry", "limit": 1}

    def test_search_tools_return_empty_result_on_network_error(self, monkeypatch):
        def fail(*args, **kwargs):
            raise requests.RequestException("boom")

        monkeypatch.setattr("tools.collaboration_tool.requests.get", fail)

        result = json.loads(collaboration_board_search(q="reply"))

        assert result["success"] is False
        assert "boom" in result["error"]
        assert result["items"] == []
        assert result["results"] == []
        assert result["count"] == 0

    def test_search_tools_return_empty_result_on_json_error(self, monkeypatch):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.url = "http://collaboration.ktl.com/api/v1/search/knowledge?query=bad"
        response.text = "not json"
        response.json.side_effect = ValueError("bad json")
        monkeypatch.setattr("tools.collaboration_tool.requests.get", Mock(return_value=response))

        result = json.loads(collaboration_search_knowledge(query="bad"))

        assert result["success"] is False
        assert "invalid JSON" in result["error"]
        assert result["items"] == []
        assert result["results"] == []
        assert result["count"] == 0

    def test_search_tools_require_query_text(self):
        knowledge = json.loads(collaboration_search_knowledge(query=""))
        board = json.loads(collaboration_board_search(q=""))

        assert knowledge["items"] == []
        assert knowledge["results"] == []
        assert knowledge["count"] == 0
        assert "query" in knowledge["error"]
        assert board["items"] == []
        assert board["results"] == []
        assert board["count"] == 0
        assert "q" in board["error"]
