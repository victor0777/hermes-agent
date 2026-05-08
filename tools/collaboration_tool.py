#!/usr/bin/env python3
"""Read-only collaboration.ktl.com integration for Hermes."""

import json
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

from tools.registry import registry

DEFAULT_BASE_URL = "http://collaboration.ktl.com"
READ_TIMEOUT_SECONDS = 10

_ENDPOINTS = {
    "dashboard": ("GET", "/api/v1/dashboard"),
    "overdue_requests": ("GET", "/api/v1/requests/overdue"),
    "blockers": ("GET", "/api/v1/blockers"),
    "reports": ("GET", "/api/v1/reports"),
    "list_requests": ("GET", "/api/v1/requests"),
    "project_summary": ("GET", "/api/v1/projects/{project}/summary"),
}

_WRITE_ACTION_HINTS = {
    "create",
    "update",
    "delete",
    "close",
    "reply",
    "respond",
    "reassign",
    "write",
    "register",
}


def _collaboration_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        config = load_config().get("collaboration", {})
        return config if isinstance(config, dict) else {}
    except Exception:
        return {}


def _base_url() -> str:
    config = _collaboration_config()
    base_url = (
        os.getenv("COLLABORATION_API_BASE")
        or os.getenv("COLLABORATION_BASE_URL")
        or config.get("base_url", DEFAULT_BASE_URL)
    )
    return str(base_url).rstrip("/")


def _headers() -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    config = _collaboration_config()
    token_env = config.get("auth_token_env", "COLLABORATION_API_TOKEN")
    token = os.getenv(str(token_env)) if token_env else None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _clean_params(params: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in params.items() if v not in (None, "", [])}


def _request_json(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{_base_url()}{path}"
    response = requests.get(
        url,
        headers=_headers(),
        params=_clean_params(params or {}),
        timeout=READ_TIMEOUT_SECONDS,
    )
    result: Dict[str, Any] = {
        "success": response.ok,
        "status_code": response.status_code,
        "url": response.url,
    }
    try:
        result["data"] = response.json()
    except ValueError:
        result["text"] = response.text[:4000]
    if not response.ok:
        result["error"] = f"Collaboration API returned HTTP {response.status_code}"
    return result


def _items(data: Any) -> List[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "requests", "reports", "blockers", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _search_error(message: str, **extra: Any) -> Dict[str, Any]:
    result = {
        "success": False,
        "error": message,
        "items": [],
        "results": [],
        "count": 0,
    }
    result.update(extra)
    return result


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _search_lists(data: Any) -> tuple[List[Any], List[Any], int]:
    if isinstance(data, list):
        return data, data, len(data)
    if not isinstance(data, dict):
        return [], [], 0

    results = data.get("results") if isinstance(data.get("results"), list) else []
    items = data.get("items") if isinstance(data.get("items"), list) else []
    nested_data = data.get("data")
    if not results and isinstance(nested_data, list):
        results = nested_data
    if not items and isinstance(nested_data, list):
        items = nested_data
    count = data.get("count")
    if not isinstance(count, int):
        count = len(results or items)
    return results, items, count


def _search_result(action: str, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = _request_json(path, params)
    except requests.RequestException as exc:
        query = urlencode(_clean_params(params))
        url = f"{_base_url()}{path}" + (f"?{query}" if query else "")
        return _search_error(f"Collaboration API request failed: {exc}", action=action, url=url)

    if "data" not in result:
        return _search_error(
            "Collaboration API returned invalid JSON",
            action=action,
            url=result.get("url"),
            status_code=result.get("status_code"),
        )

    if not result.get("success"):
        results, items, count = _search_lists(result.get("data"))
        return {
            **result,
            "action": action,
            "results": results,
            "items": items,
            "count": count,
        }

    results, items, count = _search_lists(result["data"])
    return {
        **result,
        "action": action,
        "results": results,
        "items": items,
        "count": count,
    }


def _title(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    if item.get("request_id"):
        route = f"{item.get('from') or item.get('from_project', '?')} → {item.get('to') or item.get('to_project', '?')}"
        details = []
        if item.get("owner") or item.get("assignee"):
            details.append(f"owner: {item.get('owner') or item.get('assignee')}")
        if item.get("age_days") is not None:
            details.append(f"age: {item['age_days']}d")
        suffix = f" ({', '.join(details)})" if details else ""
        return f"{item['request_id']} [{item.get('priority', 'unknown')}] {route}{suffix}"[:200]
    if item.get("project"):
        details = [str(item.get("server") or "unknown server")]
        if item.get("freshness"):
            details.append(str(item["freshness"]))
        if item.get("age_days") is not None:
            details.append(f"age: {item['age_days']}d")
        return f"{item['project']} ({', '.join(details)})"[:200]
    return str(item.get("title") or item.get("id") or item)[:200]


def _format_section(title: str, items: List[Any], empty: str) -> str:
    if not items:
        return f"{title}\n  - {empty}"
    lines = [title]
    for item in items[:5]:
        lines.append(f"  - {_title(item)}")
    if len(items) > 5:
        lines.append(f"  - ... and {len(items) - 5} more")
    return "\n".join(lines)


def _brief(limit: int = 20) -> Dict[str, Any]:
    sections: Dict[str, Dict[str, Any]] = {}
    calls = {
        "dashboard": ("/api/v1/dashboard", {}),
        "open_requests": ("/api/v1/requests", {"status": "open", "limit": limit}),
        "overdue_requests": ("/api/v1/requests/overdue", {"limit": limit}),
        "blockers": ("/api/v1/blockers", {"limit": limit}),
        "reports": ("/api/v1/reports", {"limit": limit}),
    }

    for name, (path, params) in calls.items():
        try:
            sections[name] = _request_json(path, params)
        except requests.RequestException as exc:
            sections[name] = {"success": False, "error": f"Collaboration API request failed: {exc}"}

    open_requests = _items(sections["open_requests"].get("data"))
    high_priority = [
        item for item in open_requests
        if isinstance(item, dict) and str(item.get("priority", "")).lower() == "high"
    ]
    overdue = _items(sections["overdue_requests"].get("data"))
    blockers = _items(sections["blockers"].get("data"))
    dashboard_blockers = _items(sections["dashboard"].get("data", {}).get("blockers"))
    using_blockers_fallback = False
    if not blockers and dashboard_blockers:
        blockers = dashboard_blockers
        using_blockers_fallback = True
    reports = _items(sections["reports"].get("data"))
    failed = [
        name for name, section in sections.items()
        if not section.get("success") and not (name == "blockers" and using_blockers_fallback)
    ]

    lines = ["Collaboration PM brief"]
    if failed:
        lines.append(f"Warnings: failed to read {', '.join(failed)}")
    if using_blockers_fallback:
        lines.append("Warnings: failed to read blockers endpoint; using dashboard blockers fallback")
    lines.extend([
        _format_section("High-priority open requests", high_priority, "none found"),
        _format_section("Overdue requests", overdue, "none found"),
        _format_section("Blockers", blockers, "none found"),
        _format_section("Recent reports", reports, "none found"),
    ])

    suggestions = []
    if overdue:
        suggestions.append("Review overdue requests first and decide whether to respond, reassign, or close them.")
    if blockers:
        suggestions.append("Resolve blocker ownership before starting new work.")
    if high_priority:
        suggestions.append("Pick one high-priority open request for the next action.")
    if not suggestions:
        suggestions.append("No urgent PM action found in the read-only brief.")
    lines.append(_format_section("Suggested next actions", suggestions, "none"))

    return {
        "success": not failed,
        "action": "brief",
        "sections": sections,
        "text": "\n\n".join(lines),
    }


def collaboration_tool(
    action: str,
    project: str = "",
    status: str = "",
    priority: str = "",
    kind: str = "",
    box: str = "",
    limit: int = 20,
    include_closed: bool = False,
) -> str:
    """Dispatch read-only collaboration API actions and return JSON."""
    normalized = (action or "").strip().lower()
    if not normalized:
        return json.dumps({"success": False, "error": "action is required"}, ensure_ascii=False)

    if normalized == "brief":
        return json.dumps(_brief(limit=limit), ensure_ascii=False)

    if normalized not in _ENDPOINTS:
        if any(hint in normalized for hint in _WRITE_ACTION_HINTS):
            return json.dumps(
                {
                    "success": False,
                    "error": "Write actions are not available through this read-only collaboration tool.",
                    "action": normalized,
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "success": False,
                "error": f"Unsupported collaboration action: {normalized}",
                "supported_actions": sorted(_ENDPOINTS),
            },
            ensure_ascii=False,
        )

    _, path_template = _ENDPOINTS[normalized]
    if "{project}" in path_template:
        if not project:
            return json.dumps({"success": False, "error": "project is required for this action"}, ensure_ascii=False)
        path = path_template.format(project=project)
    else:
        path = path_template

    params = {
        "project": project if normalized not in {"project_summary"} else "",
        "status": status,
        "priority": priority,
        "kind": kind,
        "box": box,
        "limit": limit,
        "include_closed": str(include_closed).lower() if include_closed else "",
    }

    try:
        result = _request_json(path, params)
        result["action"] = normalized
        return json.dumps(result, ensure_ascii=False)
    except requests.RequestException as exc:
        query = urlencode(_clean_params(params))
        url = f"{_base_url()}{path}" + (f"?{query}" if query else "")
        return json.dumps(
            {
                "success": False,
                "error": f"Collaboration API request failed: {exc}",
                "action": normalized,
                "url": url,
            },
            ensure_ascii=False,
        )


def collaboration_search_knowledge(
    query: str,
    project: str = "",
    mode: str = "auto",
    limit: int = 10,
) -> str:
    query = (query or "").strip()
    if not query:
        return json.dumps(_search_error("query is required", action="search_knowledge"), ensure_ascii=False)

    result = _search_result(
        "search_knowledge",
        "/api/v1/search/knowledge",
        {
            "query": query,
            "project": project,
            "mode": mode or "auto",
            "limit": _as_int(limit, 10),
        },
    )
    return json.dumps(result, ensure_ascii=False)


def collaboration_board_search(
    q: str,
    project: str = "",
    kind: str = "",
    status: str = "",
    category: str = "",
    limit: int = 20,
) -> str:
    q = (q or "").strip()
    if not q:
        return json.dumps(_search_error("q is required", action="board_search"), ensure_ascii=False)

    result = _search_result(
        "board_search",
        "/api/v1/board/search",
        {
            "q": q,
            "project": project,
            "kind": kind,
            "status": status,
            "category": category,
            "limit": _as_int(limit, 20),
        },
    )
    return json.dumps(result, ensure_ascii=False)


def check_collaboration_requirements() -> bool:
    return True


COLLABORATION_SEARCH_KNOWLEDGE_SCHEMA = {
    "name": "collaboration_search_knowledge",
    "description": (
        "Read-only search of collaboration knowledge and project-doc snapshots. "
        "This tool cannot create, update, or delete shared state."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query for collaboration knowledge and project snapshots.",
            },
            "project": {
                "type": "string",
                "description": "Optional project filter such as hermes-agent or OpenViking.",
                "default": "",
            },
            "mode": {
                "type": "string",
                "description": "Search mode: auto, keyword, semantic, or hybrid.",
                "default": "auto",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return.",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}


COLLABORATION_BOARD_SEARCH_SCHEMA = {
    "name": "collaboration_board_search",
    "description": (
        "Read-only search of collaboration Agent Board requests, notices, replies, and artifacts. "
        "This tool cannot create, update, or delete shared state."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "q": {
                "type": "string",
                "description": "Search query for Agent Board entries.",
            },
            "project": {
                "type": "string",
                "description": "Optional project filter.",
                "default": "",
            },
            "kind": {
                "type": "string",
                "description": "Optional board entry kind filter.",
                "default": "",
            },
            "status": {
                "type": "string",
                "description": "Optional status filter such as open or closed.",
                "default": "",
            },
            "category": {
                "type": "string",
                "description": "Optional category filter such as board_entry.",
                "default": "",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of items to return.",
                "default": 20,
            },
        },
        "required": ["q"],
    },
}


COLLABORATION_SCHEMA = {
    "name": "collaboration",
    "description": (
        "Read collaboration.ktl.com project-management state. Supports read-only actions: "
        "brief, dashboard, list_requests, overdue_requests, project_summary, blockers, reports. "
        "This tool cannot create, reply, close, reassign, or otherwise change shared state."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": sorted([*_ENDPOINTS, "brief"]),
                "description": "Read-only collaboration action to run.",
            },
            "project": {
                "type": "string",
                "description": "Project name for project_summary or filtering project-scoped lists.",
            },
            "status": {
                "type": "string",
                "description": "Optional request/report status filter when supported by the API.",
            },
            "priority": {
                "type": "string",
                "description": "Optional priority filter such as high, medium, or low.",
            },
            "kind": {
                "type": "string",
                "description": "Optional board/request kind filter when supported by the API.",
            },
            "box": {
                "type": "string",
                "description": "Optional inbox/outbox/all filter when supported by the API.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of items to request where supported.",
                "default": 20,
            },
            "include_closed": {
                "type": "boolean",
                "description": "Whether to include closed items where supported. Defaults to false.",
                "default": False,
            },
        },
        "required": ["action"],
    },
}


registry.register(
    name="collaboration",
    toolset="collaboration",
    schema=COLLABORATION_SCHEMA,
    handler=lambda args, **kw: collaboration_tool(
        action=args.get("action", ""),
        project=args.get("project", ""),
        status=args.get("status", ""),
        priority=args.get("priority", ""),
        kind=args.get("kind", ""),
        box=args.get("box", ""),
        limit=args.get("limit", 20),
        include_closed=args.get("include_closed", False),
    ),
    check_fn=check_collaboration_requirements,
    description=COLLABORATION_SCHEMA["description"],
)

registry.register(
    name="collaboration_search_knowledge",
    toolset="collaboration",
    schema=COLLABORATION_SEARCH_KNOWLEDGE_SCHEMA,
    handler=lambda args, **kw: collaboration_search_knowledge(
        query=args.get("query", ""),
        project=args.get("project", ""),
        mode=args.get("mode", "auto"),
        limit=args.get("limit", 10),
    ),
    check_fn=check_collaboration_requirements,
    description=COLLABORATION_SEARCH_KNOWLEDGE_SCHEMA["description"],
)

registry.register(
    name="collaboration_board_search",
    toolset="collaboration",
    schema=COLLABORATION_BOARD_SEARCH_SCHEMA,
    handler=lambda args, **kw: collaboration_board_search(
        q=args.get("q", ""),
        project=args.get("project", ""),
        kind=args.get("kind", ""),
        status=args.get("status", ""),
        category=args.get("category", ""),
        limit=args.get("limit", 20),
    ),
    check_fn=check_collaboration_requirements,
    description=COLLABORATION_BOARD_SEARCH_SCHEMA["description"],
)
