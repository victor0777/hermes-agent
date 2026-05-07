import json
from unittest.mock import Mock

import requests

from tools.collaboration_tool import collaboration_tool


class TestCollaborationTool:
    def test_rejects_write_like_actions(self):
        result = json.loads(collaboration_tool(action="close_request"))

        assert result["success"] is False
        assert "read-only" in result["error"]

    def test_requires_project_for_project_summary(self):
        result = json.loads(collaboration_tool(action="project_summary"))

        assert result["success"] is False
        assert "project" in result["error"]

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
