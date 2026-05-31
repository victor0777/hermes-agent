import json

from hermes_constants import get_hermes_home
from tools import security_digest_tool as digest


def _feed(tmp_path):
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
  <item>
    <title>Duplicate advisory title</title>
    <link>https://example.test/advisory/CVE-2026-0001</link>
    <pubDate>Fri, 23 May 2026 00:00:00 GMT</pubDate>
    <description>Duplicate URL should collapse in intake.</description>
  </item>
</channel></rss>
""",
        encoding="utf-8",
    )
    return feed


def test_security_news_digest_writes_local_markdown_under_hermes_home(tmp_path):
    feed = _feed(tmp_path)

    result = json.loads(
        digest.security_news_digest_tool(
            query="test security digest",
            limit=10,
            date_value="2026-05-28",
            sources=[{"name": "test-feed", "type": "rss", "path": str(feed)}],
        )
    )

    expected_path = get_hermes_home() / "digests" / "security-news" / "2026-05-28.md"
    assert result["success"] is True
    assert result["status"] == "draft_written"
    assert result["path"] == str(expected_path)
    assert result["item_count"] == 1
    assert result["approval_required_for"] == ["external_publish", "collaboration_write", "operational_action"]

    markdown = expected_path.read_text(encoding="utf-8")
    assert "# Security News Digest — 2026-05-28" in markdown
    assert "Query/topic: `test security digest`" in markdown
    assert "https://example.test/advisory/CVE-2026-0001" in markdown
    assert "Scope: local draft only" in markdown
    assert "Create collaboration/GitHub/Slack output only after explicit approval." in markdown
    assert str(expected_path).startswith(str(get_hermes_home()))


def test_security_news_digest_can_render_without_writing(tmp_path):
    feed = _feed(tmp_path)

    result = json.loads(
        digest.security_news_digest_tool(
            limit=1,
            date_value="2026-05-28",
            write_draft=False,
            sources=[{"name": "test-feed", "type": "rss", "path": str(feed)}],
        )
    )

    expected_path = get_hermes_home() / "digests" / "security-news" / "2026-05-28.md"
    assert result["success"] is True
    assert result["status"] == "draft_rendered"
    assert result["path"] == ""
    assert "Security News Digest" in result["preview"]
    assert not expected_path.exists()


def test_security_news_digest_bounds_limit_and_reports_source_errors(tmp_path):
    result = json.loads(
        digest.security_news_digest_tool(
            limit=100,
            date_value="2026-05-28",
            sources=[{"name": "missing-feed", "type": "rss", "path": str(tmp_path / "missing.xml")}],
        )
    )

    expected_path = get_hermes_home() / "digests" / "security-news" / "2026-05-28.md"
    assert result["success"] is False
    assert result["item_count"] == 0
    assert result["source_count"] == 1
    assert result["error_count"] == 1
    assert result["blockers"] == ["Configured security intelligence sources returned no candidates."]
    assert "missing-feed" in expected_path.read_text(encoding="utf-8")


def test_security_news_digest_rejects_invalid_date():
    try:
        digest.security_news_digest_tool(date_value="2026/05/28", write_draft=False, sources=[])
    except ValueError as exc:
        assert "YYYY-MM-DD" in str(exc)
    else:
        raise AssertionError("expected invalid date to raise ValueError")
