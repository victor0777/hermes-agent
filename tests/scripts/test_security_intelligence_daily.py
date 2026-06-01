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
