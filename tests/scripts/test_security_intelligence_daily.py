import json

from scripts import security_intelligence_daily as daily


def test_build_review_body_includes_collected_items(tmp_path):
    intake = tmp_path / "daily-intake.json"
    intake.write_text(
        json.dumps(
            {
                "updated_at": "2026-06-01T00:00:00Z",
                "items": [
                    {
                        "source": "test-feed",
                        "title": "Critical VPN flaw exploited",
                        "published_at": "2026-06-01T00:00:00Z",
                        "url": "https://example.test/vpn",
                        "summary": "Attackers are exploiting the issue.",
                        "cve_id": "CVE-2026-0001",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = {
        "intake_path": str(intake),
        "source_count": 1,
        "item_count": 1,
        "errors": [],
    }

    body = daily.build_review_body(result)

    assert "오늘 수집된 주요 항목" in body
    assert "[test-feed] Critical VPN flaw exploited" in body
    assert "https://example.test/vpn" in body
    assert "CVE-2026-0001" in body
    assert "작업계획" in body
    assert "실제 서버 변경" in body


def test_write_report_writes_markdown_with_items(tmp_path):
    intake = tmp_path / "daily-intake.json"
    intake.write_text(
        json.dumps(
            {
                "updated_at": "2026-06-01T00:00:00Z",
                "items": [
                    {
                        "source": "test-feed",
                        "title": "WordPress admin creation bug",
                        "published_at": "2026-06-01T00:00:00Z",
                        "url": "https://example.test/wp",
                        "summary": "Unauthenticated administrator creation.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = {
        "intake_path": str(intake),
        "source_count": 1,
        "item_count": 1,
        "errors": [],
    }

    report_path = daily.write_report(result, report_date="20260601", output_dir=str(tmp_path / "reports"))

    markdown = (tmp_path / "reports" / "security-intelligence-report-20260601.md").read_text(encoding="utf-8")
    assert report_path.endswith("security-intelligence-report-20260601.md")
    assert "# Security Intelligence Daily Report - 20260601" in markdown
    assert "WordPress admin creation bug" in markdown
    assert "https://example.test/wp" in markdown


def test_main_posts_security_category_board_request(monkeypatch, tmp_path, capsys):
    config = tmp_path / "config.yaml"
    intake = tmp_path / "daily-intake.json"
    intake.write_text(
        json.dumps(
            {
                "updated_at": "2026-06-01T00:00:00Z",
                "items": [
                    {
                        "source": "test-feed",
                        "title": "Critical VPN flaw exploited",
                        "published_at": "2026-06-01T00:00:00Z",
                        "url": "https://example.test/vpn",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config.write_text(
        f"""
collaboration:
  base_url: http://example.test
  security_intelligence:
    automation_policy: manual
    intake_path: {intake}
    report_dir: {tmp_path / "reports"}
    sources: []
""",
        encoding="utf-8",
    )
    captured = {}

    def fake_collect_security_intelligence(limit, config):
        return {
            "success": True,
            "status": "ok",
            "source_count": 1,
            "item_count": 1,
            "errors": [],
            "intake_path": str(intake),
        }

    def fake_create_collaboration_request(payload, config, idempotency_key):
        captured["payload"] = payload
        captured["config"] = config
        captured["idempotency_key"] = idempotency_key
        return {"success": True, "request_id": payload["request_id"]}

    monkeypatch.setattr(daily, "collect_security_intelligence", fake_collect_security_intelligence)
    monkeypatch.setattr(daily, "create_collaboration_request", fake_create_collaboration_request)
    monkeypatch.setattr(daily.sys, "argv", ["security_intelligence_daily.py", "--config", str(config)])

    assert daily.main() == 0
    output = json.loads(capsys.readouterr().out)

    assert output["board_request"]["success"] is True
    assert captured["payload"]["kind"] == "request"
    assert captured["payload"]["subtype"] == "security_intelligence_daily"
    assert captured["payload"]["category"] == "security"
    assert captured["payload"]["audience"] == "security"
    assert captured["payload"]["action_required"] is True
    assert captured["payload"]["automation_policy"] == "manual"
