"""Write-capable collaboration request registration helpers."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

import requests

DEFAULT_BASE_URL = "http://collaboration.ktl.com"
DEFAULT_WRITER_TOKEN_ENV = "COLLABORATION_WRITER_API_TOKEN"
LEGACY_WRITER_TOKEN_ENVS = ("COLLAB_API_KEY",)
WRITE_TIMEOUT_SECONDS = 15
AUTO_DISPATCH_POLICIES = {"auto", "auto_dispatch", "dispatch", "agent"}


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


def _writer_token(config: Dict[str, Any] | None = None) -> tuple[str, str]:
    collaboration_config = config or _collaboration_config()
    configured_env = str(collaboration_config.get("writer_auth_token_env") or DEFAULT_WRITER_TOKEN_ENV)
    token = os.getenv(configured_env) if configured_env else ""
    if token:
        return token, configured_env
    for env_name in LEGACY_WRITER_TOKEN_ENVS:
        token = os.getenv(env_name)
        if token:
            return token, env_name
    return "", configured_env or DEFAULT_WRITER_TOKEN_ENV


def _writer_headers(idempotency_key: str, config: Dict[str, Any] | None = None) -> tuple[Dict[str, str], str]:
    token, token_env = _writer_token(config)
    if not token:
        raise RuntimeError(
            f"Missing collaboration writer token. Set {token_env}; read-only dashboard tokens cannot create requests."
        )
    return (
        {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": idempotency_key,
        },
        token_env,
    )


def _response_payload(response: requests.Response) -> Dict[str, Any]:
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


def _automation_policy(payload: Dict[str, Any], config: Dict[str, Any] | None = None) -> str:
    collaboration_config = config or _collaboration_config()
    raw = (
        payload.get("automation_policy")
        or collaboration_config.get("automation_policy")
        or "manual"
    )
    return str(raw or "manual").strip().casefold()


def _should_dispatch(policy: str) -> bool:
    return policy in AUTO_DISPATCH_POLICIES


def _request_body(payload: Dict[str, Any]) -> Dict[str, Any]:
    request: Dict[str, Any] = {
        "request_id": str(payload.get("request_id") or "").strip(),
        "from_project": str(payload.get("from_project") or payload.get("from") or "hermes-agent").strip(),
        "to_project": str(payload.get("to_project") or payload.get("to") or "").strip(),
        "title": str(payload.get("title") or "").strip(),
        "status": str(payload.get("status") or "open").strip(),
        "priority": str(payload.get("priority") or "normal").strip(),
        "requester_delivery_mode": str(payload.get("requester_delivery_mode") or "notify_only").strip(),
        "requester_run_id": str(payload.get("requester_run_id") or "").strip(),
        "plan_id": str(payload.get("plan_id") or "").strip(),
        "callback_ref": str(payload.get("callback_ref") or "").strip(),
        "resume_context_ref": str(payload.get("resume_context_ref") or "").strip(),
    }
    for field in ("kind", "subtype", "audience", "category"):
        value = str(payload.get(field) or "").strip()
        if value:
            request[field] = value
    if isinstance(payload.get("action_required"), bool):
        request["action_required"] = payload["action_required"]
    return request


def _initial_thread_body(payload: Dict[str, Any]) -> str:
    body = str(payload.get("body") or "").strip()
    if body:
        return body
    details = payload.get("details")
    if isinstance(details, dict) and details:
        return json.dumps(details, ensure_ascii=False, indent=2, sort_keys=True)
    return ""


def _thread_entry_id(request_id: str, body: str) -> str:
    digest = hashlib.sha256(f"{request_id}\0{body}".encode("utf-8")).hexdigest()[:10]
    return f"hermes-request-body-{request_id}-{digest}"


def create_collaboration_request(
    payload: Dict[str, Any],
    config: Dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> Dict[str, Any]:
    """Create a collaboration v2 request and optionally attach the initial body as a thread entry."""

    request_payload = _request_body(payload)
    missing = [field for field in ("request_id", "from_project", "to_project", "title") if not request_payload[field]]
    if missing:
        return {"success": False, "error": f"Missing required collaboration request field(s): {', '.join(missing)}"}

    request_id = request_payload["request_id"]
    idem = idempotency_key or str(payload.get("client_msg_id") or f"hermes-agent-request-{request_id}")
    try:
        headers, token_env = _writer_headers(idem, config)
    except RuntimeError as exc:
        return {"success": False, "error": str(exc), "missing_writer_token": True}

    base_url = _base_url(config)
    automation_policy = _automation_policy(payload, config)
    try:
        create_response = requests.post(
            f"{base_url}/api/v2/requests",
            headers=headers,
            json=request_payload,
            timeout=WRITE_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}", "operation": "create_request"}

    create_result = _response_payload(create_response)
    result: Dict[str, Any] = {
        "success": bool(create_result.get("success")),
        "request_id": request_id,
        "idempotency_key": idem,
        "token_env": token_env,
        "automation_policy": automation_policy,
        "auto_dispatch_requested": _should_dispatch(automation_policy),
        "request": create_result,
    }
    if not create_result.get("success"):
        result["error"] = create_result.get("error", "Collaboration request create failed")
        return result

    initial_body = _initial_thread_body(payload)
    if not initial_body:
        return result

    thread_payload = {
        "entry_id": _thread_entry_id(request_id, initial_body),
        "type": "request",
        "author_project": request_payload["from_project"],
        "author_agent": "hermes-agent",
        "body": initial_body,
        "artifacts": payload.get("attachments") if isinstance(payload.get("attachments"), list) else [],
        "created_at": _utc_now(),
        "auto_dispatch": False,
        "auto_collect": True,
    }
    try:
        thread_response = requests.post(
            f"{base_url}/api/v2/orchestrator/events/thread-entry-added/{request_id}",
            headers=headers,
            json=thread_payload,
            timeout=WRITE_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        result["success"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["operation"] = "add_initial_thread_entry"
        return result

    thread_result = _response_payload(thread_response)
    result["thread_entry"] = thread_result
    result["success"] = bool(thread_result.get("success"))
    if not thread_result.get("success"):
        result["error"] = thread_result.get("error", "Collaboration initial thread entry failed")
        return result

    if not _should_dispatch(automation_policy):
        return result

    dispatch_payload = {
        "owner_project": str(
            (config or {}).get("dispatch_owner_project")
            or payload.get("dispatch_owner_project")
            or request_payload["to_project"]
        ),
        "request_id": request_id,
        "target_project": str(
            (config or {}).get("dispatch_target_project")
            or payload.get("dispatch_target_project")
            or request_payload["to_project"]
        ),
        "mission": payload.get("dispatch_mission") or None,
    }
    try:
        dispatch_response = requests.post(
            f"{base_url}/api/v2/orchestrator/dispatch-and-collect",
            headers=headers,
            json=dispatch_payload,
            timeout=WRITE_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        result["success"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["operation"] = "dispatch_and_collect"
        result["dispatch"] = {"success": False, "payload": dispatch_payload}
        return result

    dispatch_result = _response_payload(dispatch_response)
    dispatch_result["payload"] = dispatch_payload
    result["dispatch"] = dispatch_result
    result["success"] = bool(dispatch_result.get("success"))
    if not dispatch_result.get("success"):
        result["error"] = dispatch_result.get("error", "Collaboration dispatch-and-collect failed")
    return result
