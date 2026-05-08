"""Approval-gated collaboration response drafts."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

from hermes_constants import get_hermes_home
from utils import atomic_json_write

DEFAULT_BASE_URL = "http://collaboration.ktl.com"
WRITE_TIMEOUT_SECONDS = 15


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _collaboration_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        config = load_config().get("collaboration", {})
        return config if isinstance(config, dict) else {}
    except Exception:
        return {}


def _base_url(config: Dict[str, Any] | None = None) -> str:
    collaboration_config = config or _collaboration_config()
    base_url = (
        os.getenv("COLLABORATION_API_BASE")
        or os.getenv("COLLABORATION_BASE_URL")
        or collaboration_config.get("base_url", DEFAULT_BASE_URL)
    )
    return str(base_url).rstrip("/")


def _headers(config: Dict[str, Any] | None = None) -> Dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    collaboration_config = config or _collaboration_config()
    token_env = collaboration_config.get("auth_token_env", "COLLABORATION_API_TOKEN")
    token = os.getenv(str(token_env)) if token_env else None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _response_config(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    collaboration = config or _collaboration_config()
    responses = collaboration.get("responses")
    return responses if isinstance(responses, dict) else {}


def _response_outbox_path(config: Dict[str, Any] | None = None) -> Path:
    responses = _response_config(config)
    configured = responses.get("outbox_path") or (config or {}).get("response_outbox_path")
    if configured:
        return Path(str(configured)).expanduser()
    return get_hermes_home() / "collaboration" / "response_outbox.json"


def _load_response_outbox(path: Path) -> Dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        loaded = {}
    if not isinstance(loaded, dict):
        loaded = {}
    drafts = loaded.get("drafts")
    if not isinstance(drafts, dict):
        loaded["drafts"] = {}
    loaded.setdefault("version", 1)
    return loaded


def _save_response_outbox(path: Path, outbox: Dict[str, Any]) -> None:
    atomic_json_write(path, outbox, indent=2, sort_keys=True)


def _generate_action_id(request_id: str, body: str, now: str) -> str:
    digest = hashlib.sha256(f"{request_id}\0{body}\0{now}".encode("utf-8")).hexdigest()[:10]
    stamp = now.replace("-", "").replace(":", "").replace("Z", "")
    return f"collab-act-{stamp}-{digest}"


def draft_collaboration_response(request_id: str, body: str, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    request_id = (request_id or "").strip()
    body = (body or "").strip()
    if not request_id:
        return {"success": False, "error": "request_id is required"}
    if not body:
        return {"success": False, "error": "response body is required"}

    path = _response_outbox_path(config)
    outbox = _load_response_outbox(path)
    now = _utc_now()
    action_id = _generate_action_id(request_id, body, now)
    draft = {
        "action_id": action_id,
        "request_id": request_id,
        "operation": "respond",
        "body": body,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "posted_at": None,
        "posted_result": None,
    }
    outbox["drafts"][action_id] = draft
    _save_response_outbox(path, outbox)
    return {"success": True, "action_id": action_id, "draft": draft, "outbox_path": str(path)}


def list_collaboration_response_drafts(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    path = _response_outbox_path(config)
    outbox = _load_response_outbox(path)
    drafts: List[Dict[str, Any]] = [draft for draft in outbox["drafts"].values() if isinstance(draft, dict)]
    drafts.sort(key=lambda draft: str(draft.get("updated_at") or draft.get("created_at") or ""), reverse=True)
    return {"success": True, "drafts": drafts, "count": len(drafts), "outbox_path": str(path)}


def get_collaboration_response_draft(action_id: str, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    action_id = (action_id or "").strip()
    if not action_id:
        return {"success": False, "error": "action_id is required"}
    path = _response_outbox_path(config)
    outbox = _load_response_outbox(path)
    draft = outbox["drafts"].get(action_id)
    if not isinstance(draft, dict):
        return {"success": False, "error": f"No collaboration response draft found for {action_id}"}
    return {"success": True, "draft": draft, "outbox_path": str(path)}


def _post_request_response(
    request_id: str,
    body: str,
    action_id: str,
    config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    url = f"{_base_url(config)}/api/v1/board/items/{request_id}/respond"
    headers = _headers(config)
    headers["Idempotency-Key"] = action_id
    response = requests.post(
        url,
        headers=headers,
        json={"body": body, "client_msg_id": action_id},
        timeout=WRITE_TIMEOUT_SECONDS,
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


def post_collaboration_response(action_id: str, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    action_id = (action_id or "").strip()
    if not action_id:
        return {"success": False, "error": "action_id is required"}

    path = _response_outbox_path(config)
    outbox = _load_response_outbox(path)
    draft = outbox["drafts"].get(action_id)
    if not isinstance(draft, dict):
        return {"success": False, "error": f"No collaboration response draft found for {action_id}"}

    status = str(draft.get("status") or "draft")
    if status == "posted":
        return {"success": False, "error": f"Collaboration response draft {action_id} was already posted", "draft": draft}
    if status == "discarded":
        return {"success": False, "error": f"Collaboration response draft {action_id} was discarded", "draft": draft}

    request_id = str(draft.get("request_id") or "").strip()
    body = str(draft.get("body") or "").strip()
    if not request_id:
        return {"success": False, "error": "draft request_id is missing", "draft": draft}
    if not body:
        return {"success": False, "error": "draft response body is missing", "draft": draft}

    try:
        result = _post_request_response(request_id, body, action_id, config)
    except requests.RequestException as exc:
        now = _utc_now()
        draft["status"] = "failed"
        draft["updated_at"] = now
        draft["last_error"] = f"{type(exc).__name__}: {exc}"
        outbox["drafts"][action_id] = draft
        _save_response_outbox(path, outbox)
        return {"success": False, "error": draft["last_error"], "draft": draft}

    now = _utc_now()
    draft["updated_at"] = now
    if result.get("success"):
        draft["status"] = "posted"
        draft["posted_at"] = now
        draft["posted_result"] = result
        draft.pop("last_error", None)
        draft.pop("last_status_code", None)
    else:
        draft["status"] = "failed"
        draft["last_error"] = str(result.get("error") or "Collaboration response post failed")
        draft["last_status_code"] = result.get("status_code")
    outbox["drafts"][action_id] = draft
    _save_response_outbox(path, outbox)
    return {"success": bool(result.get("success")), "result": result, "draft": draft, "outbox_path": str(path)}
