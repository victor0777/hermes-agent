"""Read-only collaboration knowledge librarian digest generation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests

from hermes_constants import display_hermes_home, get_hermes_home
from tools.registry import registry
from utils import atomic_json_write

DEFAULT_BASE_URL = "http://collaboration.ktl.com"
DEFAULT_LLM_BASE_URL = "http://192.168.0.199/v1"
DEFAULT_LLM_MODEL = "qwen36-35b"
READ_TIMEOUT_SECONDS = 10
LLM_TIMEOUT_SECONDS = 60
_ENV_LOADED = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _collaboration_config(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if isinstance(config, dict):
        return config
    try:
        from hermes_cli.config import load_config

        loaded = load_config().get("collaboration", {})
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _ensure_env_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    try:
        from hermes_cli.env_loader import load_hermes_dotenv

        load_hermes_dotenv(hermes_home=get_hermes_home(), project_env=Path.cwd() / ".env")
    except Exception:
        return


def _base_url(config: Dict[str, Any] | None = None) -> str:
    _ensure_env_loaded()
    cfg = _collaboration_config(config)
    base_url = (
        os.getenv("COLLABORATION_API_BASE")
        or os.getenv("COLLABORATION_BASE_URL")
        or cfg.get("base_url")
        or DEFAULT_BASE_URL
    )
    return str(base_url).rstrip("/")


def _headers(config: Dict[str, Any] | None = None) -> Dict[str, str]:
    _ensure_env_loaded()
    headers = {"Accept": "application/json"}
    cfg = _collaboration_config(config)
    token_env = cfg.get("auth_token_env", "COLLABORATION_API_TOKEN")
    token = os.getenv(str(token_env)) if token_env else None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _clean_params(params: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in params.items() if value not in (None, "", [])}


def _get_json(path: str, params: Dict[str, Any] | None = None, *, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    response = requests.get(
        f"{_base_url(config)}{path}",
        headers=_headers(config),
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


def _items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "requests", "reports", "data", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _project_list(projects: str | Iterable[str] | None) -> List[str]:
    if not projects:
        return ["all"]
    if isinstance(projects, str):
        values = [item.strip() for item in projects.split(",")]
    else:
        values = [str(item).strip() for item in projects]
    return [value for value in values if value] or ["all"]


def _discover_project_ids(*, config: Dict[str, Any] | None = None, max_projects: int = 100) -> List[str]:
    """Discover project IDs without mutating collaboration state."""
    discovered = ["all"]
    try:
        dashboard = _get_json("/api/v1/dashboard", config=config)
    except requests.RequestException:
        return discovered
    if not dashboard.get("success"):
        return discovered
    data = dashboard.get("data")
    projects: List[str] = []
    if isinstance(data, dict):
        raw_projects = data.get("projects")
        if isinstance(raw_projects, list):
            projects = [str(item.get("project") or item.get("project_id") or "") for item in raw_projects if isinstance(item, dict)]
        elif isinstance(raw_projects, dict):
            projects = [str(key) for key in raw_projects]
    for project_id in sorted({item.strip() for item in projects if item.strip()}):
        if project_id not in discovered:
            discovered.append(project_id)
        if len(discovered) >= max_projects:
            break
    return discovered


def _source_ref(request_id: str) -> str:
    return f"collaboration:v2:request:{request_id}"


def _thread_summary(request_id: str, *, limit: int, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not request_id:
        return {"success": False, "items": [], "count": 0}
    return _get_json(
        "/api/v2/orchestrator/activation-logs",
        {"request_id": request_id, "limit": limit},
        config=config,
    )


def _knowledge_item(row: Dict[str, Any], thread_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    request_id = str(row.get("request_id") or "").strip()
    snippets = []
    for entry in thread_items[:5]:
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        body = str(
            entry.get("body")
            or entry.get("text")
            or entry.get("context_summary")
            or entry.get("summary")
            or ""
        ).strip()
        if body:
            snippets.append(
                {
                    "entry_id": str(entry.get("entry_id") or metadata.get("entry_id") or entry.get("id") or entry.get("event_id") or ""),
                    "category": str(entry.get("category") or entry.get("event_type") or ""),
                    "body_preview": " ".join(body.split())[:500],
                }
            )
    return {
        "request_id": request_id,
        "title": str(row.get("title") or ""),
        "from_project": str(row.get("from_project") or row.get("from") or ""),
        "to_project": str(row.get("to_project") or row.get("to") or ""),
        "status": str(row.get("status") or ""),
        "priority": str(row.get("priority") or ""),
        "waiting_on": str(row.get("waiting_on") or ""),
        "action": str(row.get("action") or ""),
        "next_action": str(row.get("next_action") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "last_entry_id": str(row.get("last_entry_id") or ""),
        "source_refs": [_source_ref(request_id)] if request_id else [],
        "thread_snippets": snippets,
    }


def _classify_item(item: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    request_id = item["request_id"]
    title = item["title"]
    status = item["status"].lower()
    waiting_on = item["waiting_on"].lower()
    action = item["action"].lower()
    result = {
        "decisions": [],
        "open_questions": [],
        "stale_threads": [],
        "next_actions": [],
    }
    if status in {"delivered", "closed"}:
        result["decisions"].append({"request_id": request_id, "summary": f"{status}: {title}"})
    if waiting_on in {"owner", "requester", "review"} or "reply" in action:
        result["open_questions"].append({"request_id": request_id, "summary": f"Waiting on {waiting_on or action}: {title}"})
    if action and action != "none":
        result["next_actions"].append({"request_id": request_id, "summary": f"{action}: {title}"})
    return result


def _group_by_project(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    projects: Dict[str, Dict[str, Any]] = {}
    for item in items:
        project_id = item.get("to_project") or "unknown"
        bucket = projects.setdefault(
            project_id,
            {
                "project_id": project_id,
                "items": [],
                "decisions": [],
                "open_questions": [],
                "stale_threads": [],
                "next_actions": [],
            },
        )
        bucket["items"].append(item)
        classified = _classify_item(item)
        for key, values in classified.items():
            bucket[key].extend(values)
    return projects


def _validate_index(index: Dict[str, Any]) -> Dict[str, Any]:
    missing_request_ids = []
    for item in index.get("items", []):
        if not item.get("request_id"):
            missing_request_ids.append(item.get("title") or "<untitled>")
    llm_summary = index.get("llm_summary") or {}
    llm_success = llm_summary.get("success") is True or not index.get("llm", {}).get("enabled")
    return {
        "success": not missing_request_ids and index.get("shared_state_write_attempted") is False and llm_success,
        "missing_request_ids": missing_request_ids,
        "shared_state_write_attempted": index.get("shared_state_write_attempted") is not False,
        "llm_summary_success": llm_success,
        "item_count": len(index.get("items", [])),
    }


def _default_llm_summary() -> Dict[str, Any]:
    return {
        "success": False,
        "project_topics": [],
        "decisions": [],
        "open_questions": [],
        "next_actions": [],
        "related_request_groups": [],
        "error": "",
    }


def _extract_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def _llm_input_snapshot(index: Dict[str, Any], *, max_items: int = 80) -> Dict[str, Any]:
    items = []
    for item in index.get("items", [])[:max_items]:
        items.append(
            {
                "request_id": item.get("request_id"),
                "source_refs": item.get("source_refs", []),
                "title": item.get("title"),
                "from_project": item.get("from_project"),
                "to_project": item.get("to_project"),
                "status": item.get("status"),
                "waiting_on": item.get("waiting_on"),
                "action": item.get("action"),
                "next_action": item.get("next_action"),
                "updated_at": item.get("updated_at"),
                "thread_snippets": item.get("thread_snippets", [])[:2],
            }
        )
    return {
        "period_days": index.get("period_days"),
        "item_count": len(index.get("items", [])),
        "projects": {
            project_id: {
                "item_count": len(project.get("items", [])),
                "decision_count": len(project.get("decisions", [])),
                "open_question_count": len(project.get("open_questions", [])),
                "next_action_count": len(project.get("next_actions", [])),
            }
            for project_id, project in index.get("projects", {}).items()
        },
        "items": items,
    }


def _normalize_llm_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    summary = _default_llm_summary()
    summary["success"] = True
    for key in ("project_topics", "decisions", "open_questions", "next_actions", "related_request_groups"):
        value = raw.get(key)
        summary[key] = value if isinstance(value, list) else []
    return summary


def _generate_llm_summary(index: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_env_loaded()
    base_url = index["llm"]["base_url"].rstrip("/")
    model = index["llm"]["model"]
    api_key = os.getenv("HERMES_LIBRARIAN_API_KEY") or os.getenv("OPENAI_API_KEY") or "local"
    prompt = (
        "You are a knowledge librarian for a collaboration request system. "
        "Return only a JSON object. Every entry you create must include request_ids "
        "from the provided source data when it refers to requests. Structure exactly: "
        "{"
        '"project_topics":[{"project_id":"","topic":"","request_ids":[],"source_refs":[]}],'
        '"decisions":[{"project_id":"","summary":"","request_ids":[],"source_refs":[]}],'
        '"open_questions":[{"project_id":"","question":"","request_ids":[],"source_refs":[]}],'
        '"next_actions":[{"project_id":"","action":"","request_ids":[],"source_refs":[]}],'
        '"related_request_groups":[{"theme":"","request_ids":[],"source_refs":[],"reason":""}]'
        "}. Keep summaries concise and operational. Return at most 8 entries per array."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(_llm_input_snapshot(index), ensure_ascii=False)},
        ],
        "temperature": 0.1,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        if not response.ok:
            summary = _default_llm_summary()
            summary["error"] = f"Local LLM returned HTTP {response.status_code}"
            return summary
        data = response.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
        return _normalize_llm_summary(_extract_json_object(str(content)))
    except Exception as exc:
        summary = _default_llm_summary()
        summary["error"] = str(exc)
        try:
            summary["raw_preview"] = str(content)[:1000]  # type: ignore[name-defined]
        except Exception:
            pass
        try:
            summary["finish_reason"] = str(choice.get("finish_reason", ""))  # type: ignore[name-defined]
        except Exception:
            pass
        return summary


def _render_markdown(index: Dict[str, Any]) -> str:
    lines = [
        f"# Collaboration Knowledge Librarian Digest - {index['generated_at'][:10]}",
        "",
        f"- Generated at: `{index['generated_at']}`",
        f"- Period: last {index['period_days']} day(s)",
        f"- Source base URL: `{index['source_base_url']}`",
        f"- Local LLM target: `{index['llm']['model']}` via `{index['llm']['base_url']}`",
        f"- LLM summary: {'available' if index.get('llm_summary', {}).get('success') else 'unavailable'}",
        "- Scope: read-only; no collaboration shared-state writes, closes, replies, or reassignments.",
        f"- Item count: {len(index['items'])}",
        "",
    ]
    if not index["items"]:
        lines.extend(["No recent request/response items collected.", ""])
        return "\n".join(lines)
    llm_summary = index.get("llm_summary") or {}
    if llm_summary.get("success"):
        lines.extend(["## Librarian Summary", ""])
        summary_sections = [
            ("Project Topics", "project_topics", "topic"),
            ("Decisions", "decisions", "summary"),
            ("Open Questions", "open_questions", "question"),
            ("Next Actions", "next_actions", "action"),
            ("Related Request Groups", "related_request_groups", "theme"),
        ]
        for label, key, text_key in summary_sections:
            values = llm_summary.get(key) or []
            if not values:
                continue
            lines.extend([f"### {label}", ""])
            for value in values[:20]:
                request_ids = ", ".join(f"`{request_id}`" for request_id in value.get("request_ids", []) if request_id)
                source_refs = ", ".join(f"`{ref}`" for ref in value.get("source_refs", []) if ref)
                project_id = value.get("project_id")
                prefix = f"[{project_id}] " if project_id else ""
                detail = value.get(text_key) or value.get("reason") or ""
                lines.append(f"- {prefix}{detail}")
                if request_ids:
                    lines.append(f"  - Requests: {request_ids}")
                if source_refs:
                    lines.append(f"  - Sources: {source_refs}")
            lines.append("")
    for project_id, project in sorted(index["projects"].items()):
        lines.extend([f"## {project_id}", ""])
        lines.append(f"- Items: {len(project['items'])}")
        lines.append(f"- Decisions: {len(project['decisions'])}")
        lines.append(f"- Open questions: {len(project['open_questions'])}")
        lines.append(f"- Next actions: {len(project['next_actions'])}")
        lines.append("")
        lines.append("### Recent Items")
        lines.append("")
        for item in project["items"][:20]:
            lines.append(
                f"- `{item['request_id']}` [{item['status']}/{item['waiting_on']}] "
                f"{item['from_project']} -> {item['to_project']}: {item['title']}"
            )
            if item["next_action"] or item["action"]:
                lines.append(f"  - Next/action: `{item['next_action'] or item['action']}`")
            lines.append(f"  - Source: `{item['source_refs'][0]}`")
        lines.append("")
        if project["next_actions"]:
            lines.append("### Next Action Candidates")
            lines.append("")
            for action in project["next_actions"][:10]:
                lines.append(f"- `{action['request_id']}` {action['summary']}")
            lines.append("")
    validation = index.get("validation") or {}
    lines.extend([
        "## Validation",
        "",
        f"- Request IDs present: {'yes' if not validation.get('missing_request_ids') else 'no'}",
        f"- Shared-state write attempted: {str(index.get('shared_state_write_attempted')).lower()}",
        "",
    ])
    return "\n".join(lines)


def _output_paths(output_dir: str | None, generated_at: str) -> tuple[Path, Path]:
    root = Path(output_dir).expanduser() if output_dir else get_hermes_home() / "knowledge-librarian"
    stamp = generated_at.replace(":", "").replace("-", "")
    return root / f"knowledge-index-{stamp}.json", root / f"knowledge-digest-{stamp}.md"


def generate_collaboration_librarian_digest(
    *,
    days: int = 7,
    projects: str | Iterable[str] | None = "all",
    limit: int = 100,
    include_thread_snippets: bool = True,
    use_llm_summary: bool = True,
    write_draft: bool = True,
    output_dir: str | None = None,
    config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Collect recent collaboration request/response rows and write local digest artifacts."""
    period_days = max(1, int(days or 7))
    max_items = max(1, min(int(limit or 100), 500))
    now = _utc_now()
    since = now - timedelta(days=period_days)
    generated_at = _iso(now)
    errors: List[Dict[str, Any]] = []
    rows_by_id: Dict[str, Dict[str, Any]] = {}
    requested_projects = _project_list(projects)
    source_projects = (
        _discover_project_ids(config=config)
        if requested_projects == ["all"]
        else requested_projects
    )

    for project_id in source_projects:
        try:
            result = _get_json(
                f"/api/v2/inbox/{project_id}",
                {"include_closed": "true"},
                config=config,
            )
        except requests.RequestException as exc:
            errors.append({"project": project_id, "error": str(exc)})
            continue
        if not result.get("success"):
            errors.append({"project": project_id, "error": result.get("error", "request failed")})
            continue
        for row in _items(result.get("data")):
            request_id = str(row.get("request_id") or "").strip()
            updated = _parse_timestamp(row.get("updated_at"))
            if not request_id or (updated and updated < since):
                continue
            rows_by_id[request_id] = row
            if len(rows_by_id) >= max_items:
                break

    items: List[Dict[str, Any]] = []
    for request_id, row in sorted(rows_by_id.items(), key=lambda pair: str(pair[1].get("updated_at") or ""), reverse=True):
        thread_items: List[Dict[str, Any]] = []
        if include_thread_snippets:
            try:
                thread = _thread_summary(request_id, limit=5, config=config)
                if thread.get("success"):
                    thread_items = _items(thread.get("data"))
                else:
                    errors.append({"request_id": request_id, "error": thread.get("error", "thread lookup failed")})
            except requests.RequestException as exc:
                errors.append({"request_id": request_id, "error": str(exc)})
        items.append(_knowledge_item(row, thread_items))
        if len(items) >= max_items:
            break

    index: Dict[str, Any] = {
        "version": 1,
        "generated_at": generated_at,
        "period_days": period_days,
        "source_base_url": _base_url(config),
        "source_projects": source_projects,
        "read_only": True,
        "shared_state_write_attempted": False,
        "llm": {
            "model": os.getenv("HERMES_LIBRARIAN_MODEL", DEFAULT_LLM_MODEL),
            "base_url": os.getenv("HERMES_LIBRARIAN_BASE_URL", DEFAULT_LLM_BASE_URL),
            "mode": "hermes_tool_call_digest",
            "enabled": bool(use_llm_summary),
        },
        "items": items,
        "projects": _group_by_project(items),
        "errors": errors,
    }
    index["llm_summary"] = _generate_llm_summary(index) if use_llm_summary and items else _default_llm_summary()
    if not use_llm_summary:
        index["llm_summary"]["error"] = "disabled"
    index["validation"] = _validate_index(index)
    markdown = _render_markdown(index)
    json_path, md_path = _output_paths(output_dir, generated_at)
    if write_draft:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_write(json_path, index, indent=2, sort_keys=True)
        md_path.write_text(markdown, encoding="utf-8")
    return {
        "success": index["validation"]["success"],
        "status": "draft_written" if write_draft else "draft_rendered",
        "json_path": str(json_path) if write_draft else "",
        "markdown_path": str(md_path) if write_draft else "",
        "item_count": len(items),
        "project_count": len(index["projects"]),
        "period_days": period_days,
        "request_ids": [item["request_id"] for item in items],
        "validation": index["validation"],
        "errors": errors,
        "preview": "\n".join(markdown.splitlines()[:30]),
    }


COLLABORATION_LIBRARIAN_DIGEST_SCHEMA = {
    "name": "collaboration_librarian_digest",
    "description": (
        "Read-only knowledge librarian digest for collaboration request/response activity. "
        "Reads recent collaboration v2 inbox rows, optionally looks up board snippets, and writes local JSON/Markdown drafts only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Lookback window in days. Defaults to 7.",
                "default": 7,
            },
            "projects": {
                "type": "string",
                "description": "Comma-separated project IDs to read, or all. Defaults to all.",
                "default": "all",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum request rows to include, bounded to 1-500.",
                "default": 100,
            },
            "include_thread_snippets": {
                "type": "boolean",
                "description": "Whether to run read-only board searches for request thread snippets.",
                "default": True,
            },
            "use_llm_summary": {
                "type": "boolean",
                "description": "Whether to call the local qwen36-35b endpoint for librarian summary structure.",
                "default": True,
            },
            "write_draft": {
                "type": "boolean",
                "description": "Whether to write local Markdown and JSON artifacts.",
                "default": True,
            },
            "output_dir": {
                "type": "string",
                "description": (
                    "Optional local output directory. Defaults to "
                    f"{display_hermes_home()}/knowledge-librarian."
                ),
                "default": "",
            },
        },
        "required": [],
    },
}


def collaboration_librarian_digest_tool(
    *,
    days: int = 7,
    projects: str = "all",
    limit: int = 100,
    include_thread_snippets: bool = True,
    use_llm_summary: bool = True,
    write_draft: bool = True,
    output_dir: str = "",
) -> str:
    return json.dumps(
        generate_collaboration_librarian_digest(
            days=days,
            projects=projects,
            limit=limit,
            include_thread_snippets=include_thread_snippets,
            use_llm_summary=use_llm_summary,
            write_draft=write_draft,
            output_dir=output_dir or None,
        ),
        ensure_ascii=False,
    )


registry.register(
    name="collaboration_librarian_digest",
    toolset="collaboration",
    schema=COLLABORATION_LIBRARIAN_DIGEST_SCHEMA,
    handler=lambda args, **kw: collaboration_librarian_digest_tool(
        days=args.get("days", 7),
        projects=args.get("projects", "all"),
        limit=args.get("limit", 100),
        include_thread_snippets=args.get("include_thread_snippets", True),
        use_llm_summary=args.get("use_llm_summary", True),
        write_draft=args.get("write_draft", True),
        output_dir=args.get("output_dir", ""),
    ),
    check_fn=lambda: True,
    description=COLLABORATION_LIBRARIAN_DIGEST_SCHEMA["description"],
)
