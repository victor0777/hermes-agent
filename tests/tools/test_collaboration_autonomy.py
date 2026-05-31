import json

from tools import collaboration_autonomy as autonomy


def _config(tmp_path):
    return {"autonomy_evidence_path": str(tmp_path / "evidence.json")}


def _security_config(tmp_path, sources):
    config = _config(tmp_path)
    config.update(
        {
            "security_intelligence_sources": sources,
            "security_intelligence_intake_path": str(tmp_path / "security_intake.json"),
        }
    )
    return config


def _log(tmp_path, category, event, **kwargs):
    return autonomy.append_evidence_event(category, event, config=_config(tmp_path), **kwargs)


def test_append_evidence_event_writes_local_json(tmp_path):
    result = _log(tmp_path, "Detection", "monitor_run", request_id="REQ-1", result="success")

    assert result["success"] is True
    assert result["event"]["category"] == "Detection"
    assert result["event"]["request_id"] == "REQ-1"
    payload = json.loads((tmp_path / "evidence.json").read_text())
    assert payload["events"][0]["id"] == result["event"]["id"]


def test_append_evidence_event_rejects_invalid_category(tmp_path):
    result = _log(tmp_path, "Unknown", "event")

    assert result["success"] is False
    assert "Unsupported" in result["error"]


def test_list_evidence_events_filters_and_limits(tmp_path):
    _log(tmp_path, "Detection", "monitor_run", timestamp="2026-05-09T00:00:00Z")
    _log(tmp_path, "Draft", "draft_created", timestamp="2026-05-09T00:01:00Z")
    _log(tmp_path, "Detection", "inbound_request_detected", timestamp="2026-05-09T00:02:00Z")

    result = autonomy.list_evidence_events(category="Detection", limit=1, config=_config(tmp_path))

    assert result["success"] is True
    assert result["count"] == 2
    assert len(result["events"]) == 1
    assert result["events"][0]["event"] == "inbound_request_detected"


def test_security_intelligence_intake_blocks_without_sources(tmp_path):
    result = autonomy.collect_security_intelligence(config=_security_config(tmp_path, []))

    assert result["success"] is False
    assert result["status"] == "blocked"
    assert result["blockers"] == ["No security intelligence sources configured."]
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["events"][0]["event"] == "security_intelligence_intake"
    assert evidence["events"][0]["result"] == "blocked"


def test_security_intelligence_intake_collects_rss_candidates(tmp_path):
    feed = tmp_path / "feed.xml"
    feed.write_text(
        """<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>CVE-2026-0001 actively exploited package issue</title>
    <link>https://example.test/advisory/CVE-2026-0001</link>
    <pubDate>Fri, 22 May 2026 00:00:00 GMT</pubDate>
    <description>Patch immediately for affected package versions.</description>
  </item>
</channel></rss>
""",
        encoding="utf-8",
    )

    result = autonomy.collect_security_intelligence(
        config=_security_config(tmp_path, [{"name": "test-feed", "type": "rss", "path": str(feed)}])
    )

    assert result["success"] is True
    assert result["status"] == "collected"
    assert result["item_count"] == 1
    assert result["items"][0]["source"] == "test-feed"
    assert result["items"][0]["published_at"] == "2026-05-22T00:00:00Z"
    payload = json.loads((tmp_path / "security_intake.json").read_text(encoding="utf-8"))
    assert payload["items"][0]["title"] == "CVE-2026-0001 actively exploited package issue"
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["events"][0]["metadata"]["item_count"] == 1


def test_security_intelligence_intake_collects_cisa_kev_json(tmp_path):
    feed = tmp_path / "kev.json"
    feed.write_text(
        json.dumps(
            {
                "vulnerabilities": [
                    {
                        "cveID": "CVE-2026-0002",
                        "vulnerabilityName": "Example exploited product issue",
                        "dateAdded": "2026-05-22",
                        "shortDescription": "Example KEV entry.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = autonomy.collect_security_intelligence(
        config=_security_config(tmp_path, [{"name": "cisa-kev", "type": "json", "path": str(feed)}])
    )

    assert result["success"] is True
    assert result["items"][0]["cve_id"] == "CVE-2026-0002"
    assert result["items"][0]["title"] == "Example exploited product issue"
    assert result["items"][0]["published_at"] == "2026-05-22T00:00:00Z"


def test_security_intelligence_monitor_job_spec_is_no_apply():
    spec = autonomy.security_intelligence_monitor_job_spec(schedule="every 1h")

    assert spec["name"] == "security-intelligence-intake-monitor"
    assert spec["schedule"] == "every 1h"
    assert spec["scope"] == "read_only_no_apply"
    assert "Do not apply" in spec["prompt"]


def test_compute_autonomy_kpis_rates(tmp_path):
    config = _config(tmp_path)
    autonomy.append_evidence_event("Detection", "monitor_run", result="success", timestamp="2026-05-01T00:00:00Z", config=config)
    autonomy.append_evidence_event("Detection", "monitor_run", result="failure", timestamp="2026-05-02T00:00:00Z", config=config)
    autonomy.append_evidence_event("Detection", "actual_target_request", request_id="REQ-1", timestamp="2026-05-02T00:01:00Z", config=config)
    autonomy.append_evidence_event("Detection", "inbound_request_detected", request_id="REQ-1", timestamp="2026-05-02T00:02:00Z", config=config)
    autonomy.append_evidence_event("Draft", "draft_created", request_id="REQ-1", action_id="A1", timestamp="2026-05-02T00:03:00Z", config=config)
    autonomy.append_evidence_event("Approval", "approved", action_id="A1", timestamp="2026-05-02T00:04:00Z", config=config)
    autonomy.append_evidence_event("Draft", "draft_created", request_id="REQ-2", action_id="A2", timestamp="2026-05-02T00:05:00Z", config=config)
    autonomy.append_evidence_event("Approval", "denied", action_id="A2", timestamp="2026-05-02T00:06:00Z", config=config)
    autonomy.append_evidence_event("Write", "network_write_attempted", action_id="A1", result="success", metadata={"approved": True}, timestamp="2026-05-02T00:07:00Z", config=config)
    autonomy.append_evidence_event("Write", "network_write_attempted", action_id="A2", result="failure", metadata={"approved": False}, timestamp="2026-05-02T00:08:00Z", config=config)

    kpis = autonomy.compute_autonomy_kpis(config=config)

    assert kpis["monitor_success_rate"] == 0.5
    assert kpis["detection_coverage"] == 1.0
    assert kpis["draft_acceptance_rate"] == 0.5
    assert kpis["human_denial_rate"] == 0.5
    assert kpis["post_success_rate"] == 1.0
    assert kpis["unapproved_write_count"] == 1


def test_approval_event_reconciles_write_without_approved_metadata(tmp_path):
    config = _config(tmp_path)
    autonomy.append_evidence_event("Draft", "draft_created", request_id="REQ-1", action_id="A1", timestamp="2026-05-02T00:03:00Z", config=config)
    autonomy.append_evidence_event("Approval", "approved", request_id="REQ-1", action_id="A1", timestamp="2026-05-02T00:04:00Z", config=config)
    autonomy.append_evidence_event("Write", "network_write_attempted", request_id="REQ-1", action_id="A1", result="success", metadata={"approved": False}, timestamp="2026-05-02T00:05:00Z", config=config)

    kpis = autonomy.compute_autonomy_kpis(config=config)

    assert kpis["approved_write_count"] == 1
    assert kpis["unapproved_write_count"] == 0
    assert kpis["live_hitl_handled_requests"] == 1


def test_gate_hard_fails_on_unapproved_write(tmp_path):
    _log(tmp_path, "Write", "network_write_attempted", result="success", metadata={"approved": False})

    result = autonomy.evaluate_autonomy_gate(config=_config(tmp_path))

    assert result["result"] == "Hard fail"
    assert result["autonomy_enabled"] is False
    assert result["shared_state_writes_allowed"] is False
    assert "Unapproved write" in result["reasons"][0]


def test_gate_fails_on_insufficient_sample_size(tmp_path):
    config = _config(tmp_path)
    autonomy.append_evidence_event("Detection", "monitor_run", result="success", timestamp="2026-05-09T00:00:00Z", config=config)
    autonomy.append_evidence_event("Detection", "actual_target_request", request_id="REQ-1", timestamp="2026-05-09T00:01:00Z", config=config)
    autonomy.append_evidence_event("Detection", "inbound_request_detected", request_id="REQ-1", timestamp="2026-05-09T00:02:00Z", config=config)
    autonomy.append_evidence_event("Draft", "draft_created", request_id="REQ-1", action_id="A1", timestamp="2026-05-09T00:03:00Z", config=config)
    autonomy.append_evidence_event("Approval", "approved", action_id="A1", timestamp="2026-05-09T00:04:00Z", config=config)
    autonomy.append_evidence_event("Write", "network_write_attempted", action_id="A1", result="success", metadata={"approved": True}, timestamp="2026-05-09T00:05:00Z", config=config)

    result = autonomy.evaluate_autonomy_gate(config=config)

    assert result["result"] == "Fail"
    assert any("Evaluation window" in reason for reason in result["reasons"])
    assert any("Live HITL" in reason for reason in result["reasons"])


def test_gate_pass_requires_all_thresholds_but_keeps_autonomy_disabled(tmp_path):
    config = _config(tmp_path)
    for index in range(10):
        day = index + 1
        request_id = f"REQ-{index}"
        action_id = f"A{index}"
        autonomy.append_evidence_event("Detection", "monitor_run", result="success", timestamp=f"2026-05-{day:02d}T00:00:00Z", config=config)
        autonomy.append_evidence_event("Detection", "actual_target_request", request_id=request_id, timestamp=f"2026-05-{day:02d}T00:01:00Z", config=config)
        autonomy.append_evidence_event("Detection", "inbound_request_detected", request_id=request_id, timestamp=f"2026-05-{day:02d}T00:02:00Z", config=config)
        autonomy.append_evidence_event("Draft", "draft_created", request_id=request_id, action_id=action_id, timestamp=f"2026-05-{day:02d}T00:03:00Z", config=config)
        autonomy.append_evidence_event("Approval", "approved", action_id=action_id, timestamp=f"2026-05-{day:02d}T00:04:00Z", config=config)
        autonomy.append_evidence_event("Write", "network_write_attempted", action_id=action_id, result="success", metadata={"approved": True}, timestamp=f"2026-05-{day:02d}T00:05:00Z", config=config)
    autonomy.append_evidence_event("Detection", "monitor_run", result="success", timestamp="2026-05-14T00:00:00Z", config=config)

    result = autonomy.evaluate_autonomy_gate(config=config)

    assert result["result"] == "Pass"
    assert result["autonomy_enabled"] is False
    assert result["shared_state_writes_allowed"] is False
    assert result["allowed_next_step"].startswith("Start a separate")


def test_missing_detection_coverage_prevents_pass(tmp_path):
    config = _config(tmp_path)
    for index in range(10):
        action_id = f"A{index}"
        autonomy.append_evidence_event("Detection", "monitor_run", result="success", timestamp=f"2026-05-{index + 1:02d}T00:00:00Z", config=config)
        autonomy.append_evidence_event("Draft", "draft_created", request_id=f"REQ-{index}", action_id=action_id, timestamp=f"2026-05-{index + 1:02d}T00:03:00Z", config=config)
        autonomy.append_evidence_event("Approval", "approved", action_id=action_id, timestamp=f"2026-05-{index + 1:02d}T00:04:00Z", config=config)
        autonomy.append_evidence_event("Write", "network_write_attempted", action_id=action_id, result="success", metadata={"approved": True}, timestamp=f"2026-05-{index + 1:02d}T00:05:00Z", config=config)
    autonomy.append_evidence_event("Detection", "monitor_run", result="success", timestamp="2026-05-14T00:00:00Z", config=config)

    result = autonomy.evaluate_autonomy_gate(config=config)

    assert result["result"] == "Fail"
    assert any("Detection coverage" in reason for reason in result["reasons"])


def test_forbidden_scope_safety_event_hard_fails(tmp_path):
    _log(tmp_path, "Safety", "forbidden_scope_attempt", result="blocked")

    result = autonomy.evaluate_autonomy_gate(config=_config(tmp_path))

    assert result["result"] == "Hard fail"
    assert result["kpis"]["forbidden_scope_automation_attempts"] == 1
