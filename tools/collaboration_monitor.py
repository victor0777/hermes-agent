"""Deterministic read-only collaboration PM monitoring."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from hermes_constants import get_hermes_home
from tools.collaboration_tool import collaboration_tool
from utils import atomic_json_write

SILENT_MARKER = "[SILENT]"
MONITOR_KIND_ALIASES = {
    "daily": "daily_brief",
    "daily_brief": "daily_brief",
    "urgent": "urgent_alert",
    "urgent_alert": "urgent_alert",
    "inbound": "inbound_requests",
    "inbound_requests": "inbound_requests",
    "requests": "inbound_requests",
    "new": "inbound_requests",
}
MONITOR_KINDS = frozenset(MONITOR_KIND_ALIASES.values())
MONITOR_SCHEDULE_KEYS = {
    "daily_brief": "daily_schedule",
    "urgent_alert": "urgent_schedule",
    "inbound_requests": "inbound_schedule",
}
DEFAULT_MONITOR_SCHEDULES = {
    "daily_brief": "57 8 * * *",
    "urgent_alert": "every 4h",
    "inbound_requests": "every 30m",
}
_REQUEST_ID_KEYS = ("request_id", "id")
_REQUEST_IDENTITY_FIELDS = ("title", "subject", "from", "from_project", "to", "to_project", "created_at", "date")


def normalize_monitor_kind(value: str) -> str | None:
    return MONITOR_KIND_ALIASES.get((value or "").strip().lower())


def _monitor_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        collaboration = load_config().get("collaboration", {})
        if not isinstance(collaboration, dict):
            return {}
        monitor = collaboration.get("monitor", {})
        return monitor if isinstance(monitor, dict) else {}
    except Exception:
        return {}


def _items(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("items", "requests", "blockers", "reports", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _call_collaboration(action: str, **kwargs: Any) -> Dict[str, Any]:
    try:
        return json.loads(collaboration_tool(action=action, **kwargs))
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def _log_evidence(*args: Any, **kwargs: Any) -> None:
    try:
        from tools.collaboration_autonomy import append_evidence_event

        append_evidence_event(*args, **kwargs)
    except Exception:
        return


def _item_title(item: Dict[str, Any]) -> str:
    for key in ("title", "subject", "name", "request_id", "id"):
        value = item.get(key)
        if value:
            return str(value)
    return json.dumps(item, ensure_ascii=False)[:120]


def _compact_items(items: List[Dict[str, Any]], limit: int = 5) -> List[str]:
    lines = []
    for item in items[:limit]:
        request_id = item.get("request_id") or item.get("id")
        prefix = f"{request_id}: " if request_id else ""
        priority = item.get("priority")
        suffix = f" [{priority}]" if priority else ""
        lines.append(f"- {prefix}{_item_title(item)}{suffix}")
    return lines


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _inbound_state_path(config: Dict[str, Any] | None = None) -> Path:
    configured = (config or {}).get("inbound_state_path")
    if configured:
        return Path(str(configured)).expanduser()
    return get_hermes_home() / "collaboration" / "inbound_seen_requests.json"


def _inbound_inbox_path(config: Dict[str, Any] | None = None) -> Path:
    configured = (config or {}).get("inbound_inbox_path")
    if configured:
        return Path(str(configured)).expanduser()
    return get_hermes_home() / "collaboration" / "inbound_inbox.json"


def _load_inbound_state(path: Path) -> Dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        loaded = {}
    if not isinstance(loaded, dict):
        loaded = {}
    seen = loaded.get("seen")
    if not isinstance(seen, dict):
        loaded["seen"] = {}
    loaded.setdefault("version", 1)
    return loaded


def _load_inbound_inbox(path: Path) -> Dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        loaded = {}
    if not isinstance(loaded, dict):
        loaded = {}
    items = loaded.get("items")
    if not isinstance(items, dict):
        loaded["items"] = {}
    loaded.setdefault("version", 1)
    return loaded


def _save_inbound_state(path: Path, state: Dict[str, Any]) -> None:
    atomic_json_write(path, state, indent=2, sort_keys=True)


def _save_inbound_inbox(path: Path, inbox: Dict[str, Any]) -> None:
    atomic_json_write(path, inbox, indent=2, sort_keys=True)


def _request_identity(item: Dict[str, Any]) -> str:
    for key in _REQUEST_ID_KEYS:
        value = item.get(key)
        if value:
            return str(value)
    parts = [str(item.get(key) or "") for key in _REQUEST_IDENTITY_FIELDS]
    digest = hashlib.sha256("␟".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"derived-{digest}"


def _request_metadata(item: Dict[str, Any], now: str) -> Dict[str, Any]:
    return {
        "first_seen_at": now,
        "last_seen_at": now,
        "title": _item_title(item),
        "priority": item.get("priority"),
        "project": item.get("to_project") or item.get("project"),
        "status": item.get("status"),
    }


def _inbox_item(item: Dict[str, Any], request_id: str, now: str, existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    first_seen_at = now
    status = "pending"
    if isinstance(existing, dict):
        first_seen_at = str(existing.get("first_seen_at") or now)
        status = str(existing.get("status") or "pending")
    return {
        "id": request_id,
        "request_id": item.get("request_id") or item.get("id") or request_id,
        "title": _item_title(item),
        "priority": item.get("priority"),
        "from_project": item.get("from_project") or item.get("from"),
        "to_project": item.get("to_project") or item.get("project") or item.get("to"),
        "status": status,
        "first_seen_at": first_seen_at,
        "last_seen_at": now,
        "source": "collaboration",
        "raw": {key: value for key, value in item.items() if key != "_inbound_id"},
    }


def _pending_inbox_items(inbox: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = inbox.get("items")
    if not isinstance(items, dict):
        return []
    pending = [item for item in items.values() if isinstance(item, dict) and item.get("status", "pending") == "pending"]
    return sorted(pending, key=lambda item: str(item.get("last_seen_at") or ""), reverse=True)


def build_daily_brief(limit: int = 20, project: str = "") -> Dict[str, Any]:
    result = _call_collaboration("brief", project=project, limit=limit)
    if not result.get("success"):
        error = result.get("error") or "unknown error"
        return {
            "success": False,
            "kind": "daily_brief",
            "should_notify": True,
            "severity": "error",
            "text": f"Collaboration PM daily brief failed: {error}",
            "counts": {},
            "error": error,
        }
    return {
        "success": True,
        "kind": "daily_brief",
        "should_notify": True,
        "severity": "info",
        "text": result.get("text") or json.dumps(result.get("data"), ensure_ascii=False, indent=2),
        "counts": {},
    }


def detect_inbound_requests(
    limit: int = 20,
    project: str = "",
    config: Dict[str, Any] | None = None,
    mark_seen: bool | None = None,
) -> Dict[str, Any]:
    monitor_config = {**_monitor_config(), **(config or {})}
    if mark_seen is None:
        mark_seen = bool(monitor_config.get("inbound_mark_seen_on_run", True))

    open_requests = _call_collaboration(
        "list_requests",
        project=project,
        status="open",
        limit=limit,
    )
    if not open_requests.get("success"):
        error = open_requests.get("error") or "unknown error"
        return {
            "success": False,
            "kind": "inbound_requests",
            "should_notify": True,
            "severity": "error",
            "text": f"Collaboration inbound request monitor failed: {error}",
            "counts": {},
            "error": error,
        }

    open_items = _items(open_requests.get("data"))
    state_path = _inbound_state_path(monitor_config)
    inbox_path = _inbound_inbox_path(monitor_config)
    state = _load_inbound_state(state_path)
    inbox = _load_inbound_inbox(inbox_path)
    seen = state["seen"]
    inbox_items = inbox["items"]
    now = _utc_now()

    open_items_with_ids = [
        ({**item, "_inbound_id": request_id}, request_id)
        for item in open_items
        for request_id in [_request_identity(item)]
    ]
    new_items = [item for item, request_id in open_items_with_ids if request_id not in seen]

    if mark_seen:
        seen_changed = False
        inbox_changed = False
        for item, request_id in open_items_with_ids:
            metadata = _request_metadata(item, now)
            existing_seen = seen.get(request_id)
            if isinstance(existing_seen, dict):
                metadata["first_seen_at"] = existing_seen.get("first_seen_at") or now
            seen_changed = seen_changed or existing_seen != metadata
            seen[request_id] = metadata

            existing_inbox = inbox_items.get(request_id)
            pending_item = _inbox_item(item, request_id, now, existing_inbox if isinstance(existing_inbox, dict) else None)
            inbox_changed = inbox_changed or existing_inbox != pending_item
            inbox_items[request_id] = pending_item
        if seen_changed:
            state["last_checked_at"] = now
            try:
                _save_inbound_state(state_path, state)
            except OSError as exc:
                return {
                    "success": False,
                    "kind": "inbound_requests",
                    "should_notify": True,
                    "severity": "error",
                    "text": f"Collaboration inbound request monitor failed to save seen state: {exc}",
                    "counts": {"new": len(new_items), "open": len(open_items), "seen": len(seen), "pending": len(_pending_inbox_items(inbox))},
                    "new_items": new_items,
                    "inbox_path": str(inbox_path),
                    "error": str(exc),
                }
        if inbox_changed:
            inbox["updated_at"] = now
            try:
                _save_inbound_inbox(inbox_path, inbox)
            except OSError as exc:
                return {
                    "success": False,
                    "kind": "inbound_requests",
                    "should_notify": True,
                    "severity": "error",
                    "text": f"Collaboration inbound request monitor failed to save local inbox: {exc}",
                    "counts": {"new": len(new_items), "open": len(open_items), "seen": len(seen), "pending": len(_pending_inbox_items(inbox))},
                    "new_items": new_items,
                    "inbox_path": str(inbox_path),
                    "error": str(exc),
                }

    pending_count = len(_pending_inbox_items(inbox))
    counts = {"new": len(new_items), "open": len(open_items), "seen": len(seen), "pending": pending_count}
    if not new_items:
        return {
            "success": True,
            "kind": "inbound_requests",
            "should_notify": False,
            "severity": "none",
            "text": SILENT_MARKER,
            "counts": counts,
            "new_items": [],
            "inbox_path": str(inbox_path),
        }

    lines = [
        "New collaboration requests detected",
        f"Counts: new={counts['new']}, open={counts['open']}, pending={counts['pending']}",
        "",
        "New requests:",
        *_compact_items(new_items),
        "",
        "Suggested next action: review pending items with /collab inbox before taking action. No automatic execution was performed.",
    ]
    return {
        "success": True,
        "kind": "inbound_requests",
        "should_notify": True,
        "severity": "medium",
        "text": "\n".join(lines),
        "counts": counts,
        "new_items": new_items,
        "inbox_path": str(inbox_path),
    }


def read_inbound_inbox(limit: int = 20, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    monitor_config = {**_monitor_config(), **(config or {})}
    inbox_path = _inbound_inbox_path(monitor_config)
    inbox = _load_inbound_inbox(inbox_path)
    pending_items = _pending_inbox_items(inbox)[: max(1, int(limit or 20))]
    counts = {"pending": len(_pending_inbox_items(inbox))}
    if not pending_items:
        return {
            "success": True,
            "kind": "inbound_inbox",
            "should_notify": False,
            "severity": "none",
            "text": "No pending inbound collaboration requests in the local inbox.",
            "counts": counts,
            "items": [],
            "inbox_path": str(inbox_path),
        }

    lines = [
        "Pending inbound collaboration requests",
        f"Counts: pending={counts['pending']}",
        "",
        "Pending requests:",
        *_compact_items(pending_items),
        "",
        "Suggested next action: inspect the request details before drafting any collaboration response.",
    ]
    return {
        "success": True,
        "kind": "inbound_inbox",
        "should_notify": True,
        "severity": "info",
        "text": "\n".join(lines),
        "counts": counts,
        "items": pending_items,
        "inbox_path": str(inbox_path),
    }


def evaluate_urgent_alerts(
    limit: int = 20,
    project: str = "",
    config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    monitor_config = {**_monitor_config(), **(config or {})}
    alert_on_high = bool(monitor_config.get("alert_on_high_priority", True))
    alert_on_overdue = bool(monitor_config.get("alert_on_overdue", True))
    alert_on_blockers = bool(monitor_config.get("alert_on_blockers", True))

    open_requests = _call_collaboration(
        "list_requests",
        project=project,
        status="open",
        limit=limit,
    )
    overdue = _call_collaboration("overdue_requests", project=project, limit=limit)
    blockers = _call_collaboration("blockers", project=project, limit=limit)

    failed = [
        name
        for name, result in (
            ("open requests", open_requests),
            ("overdue requests", overdue),
            ("blockers", blockers),
        )
        if not result.get("success")
    ]
    if failed:
        errors = "; ".join(
            f"{name}: {result.get('error') or 'unknown error'}"
            for name, result in (
                ("open requests", open_requests),
                ("overdue requests", overdue),
                ("blockers", blockers),
            )
            if not result.get("success")
        )
        return {
            "success": False,
            "kind": "urgent_alert",
            "should_notify": True,
            "severity": "error",
            "text": f"Collaboration PM urgent monitor failed: {errors}",
            "counts": {},
            "error": errors,
        }

    open_items = _items(open_requests.get("data"))
    high_priority = [
        item for item in open_items
        if str(item.get("priority", "")).lower() == "high"
    ]
    overdue_items = _items(overdue.get("data"))
    blocker_items = _items(blockers.get("data"))

    counts = {
        "high_priority": len(high_priority),
        "overdue": len(overdue_items),
        "blockers": len(blocker_items),
    }
    should_notify = (
        (alert_on_high and bool(high_priority))
        or (alert_on_overdue and bool(overdue_items))
        or (alert_on_blockers and bool(blocker_items))
    )
    if not should_notify:
        return {
            "success": True,
            "kind": "urgent_alert",
            "should_notify": False,
            "severity": "none",
            "text": SILENT_MARKER,
            "counts": counts,
        }

    lines = [
        "Collaboration PM alert",
        f"Counts: high_priority={counts['high_priority']}, overdue={counts['overdue']}, blockers={counts['blockers']}",
    ]
    if alert_on_high and high_priority:
        lines.extend(["", "High-priority open requests:", *_compact_items(high_priority)])
    if alert_on_overdue and overdue_items:
        lines.extend(["", "Overdue requests:", *_compact_items(overdue_items)])
    if alert_on_blockers and blocker_items:
        lines.extend(["", "Blockers:", *_compact_items(blocker_items)])
    lines.extend(["", "Suggested next action: review /collab brief and decide what needs assignment or follow-up."])

    return {
        "success": True,
        "kind": "urgent_alert",
        "should_notify": True,
        "severity": "high" if high_priority or overdue_items else "medium",
        "text": "\n".join(lines),
        "counts": counts,
    }


def run_monitor(
    kind: str,
    limit: int = 20,
    project: str = "",
    config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized = normalize_monitor_kind(kind)
    if normalized not in MONITOR_KINDS:
        return {
            "success": False,
            "kind": (kind or "").strip().lower(),
            "should_notify": True,
            "severity": "error",
            "text": f"Unsupported collaboration monitor kind: {kind}",
            "counts": {},
            "error": f"unsupported monitor kind: {kind}",
        }

    if normalized == "daily_brief":
        result = build_daily_brief(limit=limit, project=project)
    elif normalized == "inbound_requests":
        result = detect_inbound_requests(limit=limit, project=project, config=config)
    else:
        result = evaluate_urgent_alerts(limit=limit, project=project, config=config)

    _log_evidence(
        "Detection",
        "monitor_run",
        result="success" if result.get("success") else "failure",
        metadata={
            "kind": normalized,
            "project": project,
            "limit": limit,
            "should_notify": result.get("should_notify"),
            "severity": result.get("severity"),
            "counts": result.get("counts") or {},
            "error": result.get("error"),
        },
        config=config,
    )
    if normalized == "inbound_requests" and result.get("success"):
        for item in _items(result.get("new_items")):
            request_id = str(item.get("_inbound_id") or _request_identity(item))
            _log_evidence(
                "Detection",
                "inbound_request_detected",
                request_id=request_id,
                result="success",
                metadata={"kind": normalized, "project": project, "title": _item_title(item)},
                config=config,
            )
    if normalized == "urgent_alert" and result.get("success") and result.get("should_notify"):
        _log_evidence(
            "Detection",
            "urgent_alert_detected",
            result="success",
            metadata={"kind": normalized, "project": project, "counts": result.get("counts") or {}},
            config=config,
        )
    if not result.get("success"):
        _log_evidence(
            "Failure",
            "api_failure",
            result="failure",
            metadata={"kind": normalized, "project": project, "error": result.get("error")},
            config=config,
        )
    return result
