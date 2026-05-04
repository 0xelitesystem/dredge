"""CourtListener: U.S. federal and many state court records.

Free API. A token grants higher rate limits but is not required.
API docs: https://www.courtlistener.com/help/api/rest/
"""

from datetime import datetime, timezone
from typing import Optional

import httpx

from ..core.investigator import Investigator
from ..core.models import Finding, SourceType, Target


BASE_URL = "https://www.courtlistener.com/api/rest/v3/search/"
MAX_RESULTS_PER_NAME = 50


def _parse_iso(d: Optional[str]) -> Optional[datetime]:
    if not d:
        return None
    try:
        dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


class CourtListenerInvestigator(Investigator):
    name = "courtlistener"
    description = "U.S. federal and state court records."
    requires_keys = []
    supports_types = ["person", "company"]

    async def investigate(self, target: Target) -> list[Finding]:
        headers: dict[str, str] = {}
        token = self.config.get("COURTLISTENER_TOKEN")
        if token:
            headers["Authorization"] = f"Token {token}"

        findings: list[Finding] = []
        seen_urls: set[str] = set()

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for name in target.all_names:
                results = await self._search(client, name)
                for item in results[:MAX_RESULTS_PER_NAME]:
                    finding = self._to_finding(name, item)
                    if finding and finding.url not in seen_urls:
                        seen_urls.add(finding.url)
                        findings.append(finding)

        return findings

    async def _search(self, client: httpx.AsyncClient, name: str) -> list[dict]:
        params = {
            "q": f'"{name}"',
            "type": "r",  # RECAP / federal court documents
            "order_by": "dateFiled desc",
        }
        try:
            r = await client.get(BASE_URL, params=params)
            r.raise_for_status()
            return r.json().get("results", []) or []
        except (httpx.HTTPError, ValueError):
            return []

    def _to_finding(self, queried_name: str, item: dict) -> Optional[Finding]:
        case_name = item.get("caseName") or item.get("case_name") or ""
        if not case_name:
            return None
        court = item.get("court", "")
        date_filed = item.get("dateFiled") or item.get("date_filed")
        absolute_url = item.get("absolute_url", "") or ""
        url = f"https://www.courtlistener.com{absolute_url}" if absolute_url else ""
        title = f"{case_name} ({court})" if court else case_name

        return Finding(
            investigator=self.name,
            title=title,
            url=url,
            snippet=item.get("snippet") or f"Filed {date_filed}" if date_filed else case_name,
            source_type=SourceType.COURT_RECORD,
            timestamp=_parse_iso(date_filed),
            raw={
                "queried_name": queried_name,
                "docket_number": item.get("docketNumber") or item.get("docket_number", ""),
                "court": court,
            },
        )
