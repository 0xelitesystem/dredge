"""Render an InvestigationResult as a markdown report."""

import re
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote

from ..core.models import Finding, InvestigationResult, SourceType


# Sort key for findings without a timestamp; tz-aware so it's safe to compare.
_DT_MIN = datetime.min.replace(tzinfo=timezone.utc)

# Titles, URLs and snippets come from the investigated party's own pages, so
# they are escaped: no images, links, raw HTML, or forged headings when the
# report is viewed. Only characters that can start those are touched, so
# ordinary titles ("A & B | Site", "about_us") come out unchanged.
_NEWLINES = re.compile(r"\r\n|[\r\n]")
_ENTITY_AMP = re.compile(r"&(?=#?[0-9A-Za-z]+;)")
_MD_INLINE = re.compile(r"[\\`\[\]]")
_BLOCK_MARKER = re.compile(r"^(\s*)([#>+*_~-])")
_ORDERED_MARKER = re.compile(r"^(\s*\d{1,9})([.)])")
_URL_UNSAFE = re.compile(r"[\s\x00-\x1f\x7f<>`]")
_URL_ESCAPE = re.compile(r"[\\()]")


def _md(text) -> str:
    """Escape untrusted text so Markdown and HTML show it literally, on one line."""
    text = _NEWLINES.sub(" ", str(text))
    text = _ENTITY_AMP.sub("&amp;", text).replace("<", "&lt;")
    return _MD_INLINE.sub(r"\\\g<0>", text)


def _md_line(text) -> str:
    """Like _md, for text that starts its own line: block markers stay literal.

    Bare <mark></mark> tags (no attributes) are kept so search-hit highlighting
    still renders; they cannot load anything.
    """
    text = _BLOCK_MARKER.sub(r"\1\\\2", _md(text))
    text = _ORDERED_MARKER.sub(r"\1\\\2", text)
    return text.replace("&lt;mark>", "<mark>").replace("&lt;/mark>", "</mark>")


def _md_url(url) -> str:
    """Return url as a link destination it cannot break out of; '' if not http(s)."""
    url = str(url)
    if not url.lower().startswith(("http://", "https://")):
        return ""
    url = _URL_UNSAFE.sub(lambda m: quote(m.group(), safe=""), url)
    return _URL_ESCAPE.sub(r"\\\g<0>", url)


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

    out.append(f"# Investigation: {_md(target.name)}")
    out.append("")
    out.append(f"- Type: `{target.type.value}`")
    if target.aliases:
        out.append(f"- Aliases: {', '.join(_md(a) for a in target.aliases)}")
    if target.known_domains:
        out.append(f"- Known domains: {', '.join(_md(d) for d in target.known_domains)}")
    out.append(f"- Started: {result.started_at.isoformat(timespec='seconds')}")
    if result.completed_at:
        out.append(f"- Completed: {result.completed_at.isoformat(timespec='seconds')}")
    out.append(f"- Total findings: {len(result.findings)}")
    out.append("")

    if result.errors:
        out.append("## Errors")
        out.append("")
        for err in result.errors:
            out.append(f"- {_md(err)}")
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
            ts = f.timestamp.strftime("%Y-%m-%d") if f.timestamp else "undated"
            title = _md(f.title or "(untitled)")
            url = _md_url(f.url) if f.url else ""
            if url:
                out.append(f"### [{title}]({url})")
            else:
                out.append(f"### {title}")
            out.append(f"`{ts}` · `{f.investigator}`")
            out.append("")
            if f.snippet:
                out.append(_md_line(f.snippet))
                out.append("")
        out.append("")

    out.append("---")
    out.append("")
    out.append(
        "Findings are unverified raw evidence. "
        "Read the primary source before drawing conclusions."
    )

    return "\n".join(out)
