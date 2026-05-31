#!/usr/bin/env python3
"""Daily no-apply security intelligence intake orchestration.

Hermes owns source fetching and intake storage. cybersecurity-agent owns
no-apply risk review and work-plan reporting from the produced intake.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "tools"))

from collaboration_autonomy import collect_security_intelligence  # noqa: E402
from collaboration_requests import create_collaboration_request  # noqa: E402

DEFAULT_CONFIG = Path.home() / ".hermes" / "config.yaml"
VIRTUAL_PROJECT_ID = "security-intelligence-policy-loop"
DEFAULT_AUTOMATION_POLICY = "auto"
ALLOWED_AUTOMATION_POLICIES = {"manual", "auto", "auto_dispatch", "dispatch", "agent"}


def load_yaml(path: Path) -> dict:
    try:
        loaded = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def build_review_body(result: dict) -> str:
    intake_path = result.get("intake_path", "")
    item_count = result.get("item_count", 0)
    source_count = result.get("source_count", 0)
    error_count = len(result.get("errors") or [])
    updated_at = ""
    try:
        payload = json.loads(Path(intake_path).read_text())
        updated_at = payload.get("updated_at", "")
    except Exception:
        pass

    return f"""Hermes가 승인된 보안 인텔리전스 소스를 주기 수집했고, 아래 intake를 생성했습니다. cybersecurity-agent는 이 intake를 읽고 no-apply 검토와 작업계획을 작성해 주세요.

Hermes intake:
- path: `{intake_path}`
- updated_at: `{updated_at}`
- source_count: {source_count}
- item_count: {item_count}
- error_count: {error_count}

요청 작업:
1. intake 후보를 읽고 중복/후보 정리를 수행합니다.
2. 각 항목에 대해 관리 서버/프로젝트 관련성, 위험도, 신뢰도, 근거 부족 여부를 평가합니다.
3. medium/high 또는 evidence-insufficient 항목은 `/home/ktl/projects/cybersecurity-agent/reports/security-intelligence/` 아래 no-apply 리스크 리포트 또는 작업계획 초안으로 남깁니다.
4. 사용자에게 보고할 요약에는 위험도, 근거, 불확실성, 다음 승인 필요 작업을 구분합니다.

금지/중단 조건:
- 정책 결정, 룰 활성화, 탐지/스캐너/런북 적용, 서버 변경, credential 접근 금지.
- confirmed affected-server 주장은 authoritative affected/fixed version evidence와 approved managed-asset package inventory가 있을 때만 허용합니다.
- 근거가 부족하면 실패 처리하지 말고 risk/confidence/caveat 중심의 no-apply 리포트로 남깁니다.
- source list, cadence, participant, blast radius 확장은 별도 승인 전까지 하지 않습니다.
"""


def resolve_automation_policy(security_config: dict) -> str:
    """Return the collaboration automation policy for the daily handoff."""
    raw = (
        os.environ.get("COLLAB_SECURITY_INTELLIGENCE_AUTOMATION_POLICY")
        or security_config.get("automation_policy")
        or DEFAULT_AUTOMATION_POLICY
    )
    policy = str(raw).strip().casefold()
    if policy not in ALLOWED_AUTOMATION_POLICIES:
        raise ValueError(
            "invalid automation policy for security intelligence handoff: "
            f"{raw!r}; expected one of {sorted(ALLOWED_AUTOMATION_POLICIES)}"
        )
    return policy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true", help="collect only; do not create a board request")
    args = parser.parse_args()

    full_config = load_yaml(Path(args.config))
    collaboration = full_config.get("collaboration") if isinstance(full_config.get("collaboration"), dict) else {}
    security = collaboration.get("security_intelligence") if isinstance(collaboration.get("security_intelligence"), dict) else {}
    autonomy = collaboration.get("autonomy") if isinstance(collaboration.get("autonomy"), dict) else {}

    collect_config = {
        "security_intelligence_sources": security.get("sources", []),
        "security_intelligence_intake_path": security.get(
            "intake_path",
            "/home/ktl/projects/hermes-agent/data/security-intelligence/daily-intake.json",
        ),
        "security_intelligence_fetch_timeout_seconds": security.get("fetch_timeout_seconds", 20),
        "evidence_log_path": autonomy.get(
            "evidence_log_path",
            "/home/ktl/projects/hermes-agent/data/security-intelligence/autonomy-evidence.json",
        ),
    }
    result = collect_security_intelligence(limit=args.limit, config=collect_config)
    automation_policy = resolve_automation_policy(security)

    output = {
        "collected": result.get("success"),
        "status": result.get("status"),
        "source_count": result.get("source_count"),
        "item_count": result.get("item_count"),
        "error_count": len(result.get("errors") or []),
        "intake_path": result.get("intake_path"),
        "automation_policy": automation_policy,
        "board_request": None,
    }

    if result.get("success") and not args.dry_run:
        kst_today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
        idempotency_key = f"hermes-security-intel-daily-{kst_today}"
        api_base = os.environ.get("COLLABORATION_API_BASE") or os.environ.get("COLLAB_API_BASE") or collaboration.get("base_url") or "http://192.168.0.193:7851"
        payload = {
            "request_id": f"REQ-HERMES-SECURITY-INTEL-{kst_today}",
            "from_project": "hermes-agent",
            "to_project": "cybersecurity-agent",
            "priority": "medium",
            "title": f"Daily security intelligence review from Hermes intake {kst_today}",
            "body": build_review_body(result),
            "attachments": [
                "virtual_projects/security-intelligence-policy-loop/plan.md",
                "virtual_projects/security-intelligence-policy-loop/sources/security-intelligence-sources.json",
            ],
            "client_msg_id": idempotency_key,
        }
        output["board_request"] = create_collaboration_request(
            payload,
            config={
                "base_url": api_base,
                "writer_auth_token_env": collaboration.get("writer_auth_token_env", "COLLABORATION_WRITER_API_TOKEN"),
            },
            idempotency_key=idempotency_key,
        )

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
