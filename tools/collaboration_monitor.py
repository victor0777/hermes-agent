"""Deterministic read-only collaboration PM monitoring."""

import json
from typing import Any, Dict, List

from tools.collaboration_tool import collaboration_tool

SILENT_MARKER = "[SILENT]"
_MONITOR_KINDS = {"daily_brief", "urgent_alert"}


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
    normalized = (kind or "").strip().lower()
    if normalized not in _MONITOR_KINDS:
        return {
            "success": False,
            "kind": normalized,
            "should_notify": True,
            "severity": "error",
            "text": f"Unsupported collaboration monitor kind: {kind}",
            "counts": {},
            "error": f"unsupported monitor kind: {kind}",
        }

    if normalized == "daily_brief":
        return build_daily_brief(limit=limit, project=project)
    return evaluate_urgent_alerts(limit=limit, project=project, config=config)
