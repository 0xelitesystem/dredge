"""Render an InvestigationResult as a markdown report."""

from collections import defaultdict
from datetime import datetime, timezone

from ..core.models import Finding, InvestigationResult, SourceType


# Sort key for findings without a timestamp; tz-aware so it's safe to compare.
_DT_MIN = datetime.min.replace(tzinfo=timezone.utc)


SECTION_ORDER: list[tuple[SourceType, str]] = [
    (SourceType.COURT_RECORD, "Court Records"),
    (SourceType.REGULATORY_FILING, "Regulatory Filings"),
    (SourceType.DELETED_CONTENT, "Deleted Content"),
    (SourceType.ARCHIVED_PAGE, "Archived Pages"),
    (SourceType.SEARCH_RESULT, "Search Results"),
    (SourceType.SOCIAL_MEDIA, "Social Media"),
    (SourceType.NEWS_ARTICLE, "News Articles"),
    (SourceType.ON_CHAIN, "On-Chain Activity"),
]


def render(result: InvestigationResult) -> str:
    target = result.target
    out: list[str] = []

    out.append(f"# Investigation: {target.name}")
    out.append("")
    out.append(f"- Type: `{target.type.value}`")
    if target.aliases:
        out.append(f"- Aliases: {', '.join(target.aliases)}")
    if target.known_domains:
        out.append(f"- Known domains: {', '.join(target.known_domains)}")
    out.append(f"- Started: {result.started_at.isoformat(timespec='seconds')}")
    if result.completed_at:
        out.append(f"- Completed: {result.completed_at.isoformat(timespec='seconds')}")
    out.append(f"- Total findings: {len(result.findings)}")
    out.append("")

    if result.errors:
        out.append("## Errors")
        out.append("")
        for err in result.errors:
            out.append(f"- {err}")
        out.append("")

    by_source: dict[SourceType, list[Finding]] = defaultdict(list)
    for f in result.findings:
        by_source[f.source_type].append(f)

    for source_type, heading in SECTION_ORDER:
        items = by_source.get(source_type, [])
        if not items:
            continue
        out.append(f"## {heading} ({len(items)})")
        out.append("")
        ordered = sorted(items, key=lambda x: x.timestamp or _DT_MIN, reverse=True)
        for f in ordered:
            ts = f.timestamp.strftime("%Y-%m-%d") if f.timestamp else "—"
            title = f.title or "(untitled)"
            if f.url:
                out.append(f"### [{title}]({f.url})")
            else:
                out.append(f"### {title}")
            out.append(f"`{ts}` · `{f.investigator}`")
            out.append("")
            if f.snippet:
                out.append(f.snippet)
                out.append("")
        out.append("")

    out.append("---")
    out.append("")
    out.append(
        "Findings are unverified raw evidence. "
        "Read the primary source before drawing conclusions."
    )

    return "\n".join(out)
