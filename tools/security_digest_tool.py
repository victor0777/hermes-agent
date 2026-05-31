"""Security news digest tool for local read/write-only intelligence drafts."""

import json
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List

from hermes_constants import get_hermes_home
from tools.registry import registry

DEFAULT_QUERY = "cybersecurity vulnerability exploit patch advisory"
DEFAULT_SOURCES = [
    {
        "name": "CISA Cybersecurity Advisories",
        "url": "https://www.cisa.gov/cybersecurity-advisories/all.xml",
        "type": "rss",
    },
]

SECURITY_NEWS_DIGEST_SCHEMA = {
    "name": "security_news_digest",
    "description": (
        "Collect security news/advisory candidates from read-only sources and write a local Markdown digest. "
        "This tool only creates local drafts under Hermes home; it does not publish externally or take action."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Topic label for the digest. Sources are configured separately; this is recorded in the local draft.",
                "default": DEFAULT_QUERY,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of items to include, bounded to 1-25.",
                "default": 10,
            },
            "date": {
                "type": "string",
                "description": "Digest date in YYYY-MM-DD format. Defaults to today in UTC.",
            },
            "write_draft": {
                "type": "boolean",
                "description": "Whether to write the local Markdown digest file.",
                "default": True,
            },
            "sources": {
                "type": "array",
                "description": "Optional read-only RSS/JSON sources. Each item may include name, url/path, and type.",
                "items": {"type": "object"},
            },
        },
        "required": [],
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digest_date(value: str | None) -> str:
    if not value:
        return date.today().isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError("date must use YYYY-MM-DD format") from exc


def _bounded_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 10
    return max(1, min(parsed, 25))


def _normalize_sources(sources: Any) -> List[Dict[str, Any]]:
    if not sources:
        return [source.copy() for source in DEFAULT_SOURCES]
    if not isinstance(sources, list):
        raise ValueError("sources must be a list")
    normalized = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        copied = source.copy()
        if copied.get("url") or copied.get("path"):
            copied.setdefault("type", "rss")
            normalized.append(copied)
    return normalized or [source.copy() for source in DEFAULT_SOURCES]


def _plain(value: Any) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return " ".join(text.split())


def _markdown_link(title: str, url: str) -> str:
    safe_title = title.replace("[", "\\[").replace("]", "\\]") or url or "Untitled"
    if url.startswith(("http://", "https://")):
        return f"[{safe_title}]({url})"
    return safe_title


def _severity_bucket(item: Dict[str, Any]) -> str:
    severity = str(item.get("severity") or "").strip().lower()
    title = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    if severity in {"critical", "high", "medium", "low"}:
        return severity.title()
    if any(term in title for term in ("critical", "actively exploited", "rce", "remote code execution")):
        return "High"
    if any(term in title for term in ("vulnerability", "exploit", "patch", "advisory", "cve-")):
        return "Medium"
    return "Review"


def _render_digest(*, digest_date: str, query: str, collected: Dict[str, Any], generated_at: str) -> str:
    items = collected.get("items") or []
    errors = collected.get("errors") or []
    lines = [
        f"# Security News Digest — {digest_date}",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Query/topic: `{query}`",
        f"- Source count: {collected.get('source_count', 0)}",
        f"- Item count: {len(items)}",
        "- Scope: local draft only; external publishing or operational action requires approval.",
        "",
        "## Executive Summary",
        "",
    ]
    if items:
        high_count = sum(1 for item in items if _severity_bucket(item) == "High")
        cve_count = sum(1 for item in items if item.get("cve_id"))
        lines.extend([
            f"- Reviewed {len(items)} security news/advisory candidates from read-only sources.",
            f"- {high_count} item(s) need high-priority review based on title/summary signals.",
            f"- {cve_count} item(s) include an explicit CVE identifier.",
        ])
    else:
        lines.append("- No candidate items were collected; check source configuration and network access.")
    lines.extend(["", "## Notable Items", ""])
    if items:
        for idx, item in enumerate(items, 1):
            title = _plain(item.get("title")) or "Untitled"
            url = str(item.get("url") or "")
            source = _plain(item.get("source") or item.get("source_name"))
            published = _plain(item.get("published_at")) or "unknown"
            summary = _plain(item.get("summary"))
            cve_id = _plain(item.get("cve_id"))
            lines.append(f"### {idx}. {_markdown_link(title, url)}")
            lines.append("")
            lines.append(f"- Source: {source or 'unknown'}")
            lines.append(f"- Published: {published}")
            lines.append(f"- Review priority: {_severity_bucket(item)}")
            if cve_id:
                lines.append(f"- CVE: `{cve_id}`")
            if summary:
                lines.append(f"- Summary: {summary}")
            lines.append("")
    else:
        lines.append("No items collected.")
        lines.append("")
    lines.extend([
        "## Suggested Local Follow-up",
        "",
        "- Ask Hermes to cluster related items and draft a human-readable briefing if needed.",
        "- Create collaboration/GitHub/Slack output only after explicit approval.",
        "- Do not apply policy, credential, scheduler, infrastructure, or production changes from this digest alone.",
        "",
    ])
    if errors:
        lines.extend(["## Source Errors", ""])
        for error in errors:
            lines.append(f"- {error.get('source', 'unknown')}: {error.get('error', '')}")
        lines.append("")
    return "\n".join(lines)


def security_news_digest_tool(
    *,
    query: str = DEFAULT_QUERY,
    limit: int = 10,
    date_value: str | None = None,
    write_draft: bool = True,
    sources: Any = None,
) -> str:
    from tools.collaboration_autonomy import collect_security_intelligence

    digest_date = _digest_date(date_value)
    bounded_limit = _bounded_limit(limit)
    normalized_sources = _normalize_sources(sources)
    config = {"security_intelligence_sources": normalized_sources}
    collected = collect_security_intelligence(limit=bounded_limit, config=config)
    generated_at = _utc_now()
    markdown = _render_digest(
        digest_date=digest_date,
        query=str(query or DEFAULT_QUERY),
        collected=collected,
        generated_at=generated_at,
    )
    output_path = get_hermes_home() / "digests" / "security-news" / f"{digest_date}.md"
    if write_draft:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    preview = "\n".join(markdown.splitlines()[:18])
    return json.dumps(
        {
            "success": bool(collected.get("items")),
            "status": "draft_written" if write_draft else "draft_rendered",
            "path": str(output_path) if write_draft else "",
            "item_count": len(collected.get("items") or []),
            "source_count": collected.get("source_count", 0),
            "error_count": len(collected.get("errors") or []),
            "preview": preview,
            "approval_required_for": ["external_publish", "collaboration_write", "operational_action"],
            "intake_path": collected.get("intake_path", ""),
            "blockers": collected.get("blockers", []),
        },
        ensure_ascii=False,
    )


registry.register(
    name="security_news_digest",
    toolset="collaboration",
    schema=SECURITY_NEWS_DIGEST_SCHEMA,
    handler=lambda args, **kw: security_news_digest_tool(
        query=args.get("query", DEFAULT_QUERY),
        limit=args.get("limit", 10),
        date_value=args.get("date"),
        write_draft=args.get("write_draft", True),
        sources=args.get("sources"),
    ),
    check_fn=lambda: True,
    description=SECURITY_NEWS_DIGEST_SCHEMA["description"],
)
