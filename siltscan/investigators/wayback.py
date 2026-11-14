"""Wayback Machine: snapshots and deleted-content detection.

Two passes per known domain:
1. Pull the URL inventory from the CDX API.
2. For URLs that were once 2xx and later 4xx/5xx, surface them
   as likely deletions with a link to the last live snapshot.

No API key required. CDX rate-limits aggressive use; one
investigation per few seconds is fine.
"""

from datetime import datetime, timezone
from typing import Optional

import httpx

from ..core.investigator import Investigator
from ..core.models import Finding, SourceType, Target


CDX_URL = "https://web.archive.org/cdx/search/cdx"
SNAPSHOTS_PER_DOMAIN = 1000  # cap for v0
ARCHIVED_SAMPLE = 25  # how many "page existed" results to surface per domain


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _format_ts(ts: str) -> str:
    dt = _parse_ts(ts)
    return dt.strftime("%Y-%m-%d") if dt else ts


class WaybackInvestigator(Investigator):
    name = "wayback"
    description = "Internet Archive snapshots and deleted-content detection."
    requires_keys = []
    supports_types = ["person", "company", "domain"]

    async def investigate(self, target: Target) -> list[Finding]:
        if not target.known_domains:
            return []

        findings: list[Finding] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for domain in target.known_domains:
                snapshots = await self._fetch(client, domain)
                findings.extend(self._sample_archived(domain, snapshots))
                findings.extend(self._detect_deletions(domain, snapshots))

        return findings

    async def _fetch(self, client: httpx.AsyncClient, domain: str) -> list[list[str]]:
        params = {
            "url": f"{domain}/*",
            "output": "json",
            "fl": "timestamp,original,statuscode",
            "limit": SNAPSHOTS_PER_DOMAIN,
        }
        try:
            r = await client.get(CDX_URL, params=params)
            r.raise_for_status()
            data = r.json()
            return data[1:] if isinstance(data, list) and len(data) > 1 else []
        except (httpx.HTTPError, ValueError):
            return []

    def _sample_archived(self, domain: str, snapshots: list[list[str]]) -> list[Finding]:
        out: list[Finding] = []
        seen_urls: set[str] = set()
        for row in snapshots:
            if len(row) < 3:
                continue
            ts, url, status = row[0], row[1], row[2]
            if url in seen_urls or not status.startswith("2"):
                continue
            seen_urls.add(url)
            out.append(Finding(
                investigator=self.name,
                title=f"Archived: {url}",
                url=f"https://web.archive.org/web/{ts}/{url}",
                snippet=f"Snapshot from {_format_ts(ts)} (HTTP {status})",
                source_type=SourceType.ARCHIVED_PAGE,
                timestamp=_parse_ts(ts),
                raw={"domain": domain, "original_url": url, "status": status},
            ))
            if len(out) >= ARCHIVED_SAMPLE:
                break
        return out

    def _detect_deletions(self, domain: str, snapshots: list[list[str]]) -> list[Finding]:
        last_alive: dict[str, str] = {}
        last_status: dict[str, tuple[str, str]] = {}

        for row in snapshots:
            if len(row) < 3:
                continue
            ts, url, status = row[0], row[1], row[2]
            last_status[url] = (ts, status)
            if status.startswith("2"):
                last_alive[url] = ts

        findings: list[Finding] = []
        for url, (ts, status) in last_status.items():
            if status[:1] in ("4", "5") and url in last_alive:
                alive_ts = last_alive[url]
                findings.append(Finding(
                    investigator=self.name,
                    title=f"Likely deleted: {url}",
                    url=f"https://web.archive.org/web/{alive_ts}/{url}",
                    snippet=(
                        f"Page was last archived alive on {_format_ts(alive_ts)}, "
                        f"later returned HTTP {status} on {_format_ts(ts)}."
                    ),
                    source_type=SourceType.DELETED_CONTENT,
                    timestamp=_parse_ts(alive_ts),
                    raw={
                        "domain": domain,
                        "url": url,
                        "last_alive": alive_ts,
                        "last_status": status,
                        "last_status_ts": ts,
                    },
                ))
        return findings
