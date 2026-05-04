"""Google search via SerpAPI, with adversarial keyword expansion.

SerpAPI is used because it returns a clean structured payload and
handles paging. The investigator is intentionally search-engine-agnostic
beneath: swap `_run_query` to use Brave Search, SearXNG, Google CSE,
or Kagi without touching the rest.
"""

import asyncio
from urllib.parse import urlparse

import httpx

from ..core.investigator import Investigator
from ..core.keywords import build_queries
from ..core.models import Finding, SourceType, Target


class GoogleDorkInvestigator(Investigator):
    name = "google_dork"
    description = "Google search via SerpAPI with adversarial query expansion."
    requires_keys = ["SERPAPI_KEY"]
    supports_types = ["person", "company", "domain"]

    BASE_URL = "https://serpapi.com/search"

    async def investigate(self, target: Target) -> list[Finding]:
        clusters = ["fraud", "legal", "reputation"]
        if target.type.value in ("company", "domain"):
            clusters.append("financial")

        max_queries = int(self.config.get("DREDGE_MAX_QUERIES", "20"))

        queries = build_queries(
            target.name,
            clusters=clusters,
            exclude_domains=target.known_domains,
            max_queries=max_queries,
        )

        seen: set[str] = set()
        findings: list[Finding] = []

        async with httpx.AsyncClient(timeout=30) as client:
            tasks = [self._run_query(client, q) for q in queries]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for query, items in zip(queries, results):
                if isinstance(items, BaseException):
                    continue
                for item in items:
                    url = item.get("link") or item.get("url")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    findings.append(Finding(
                        investigator=self.name,
                        title=item.get("title", ""),
                        url=url,
                        snippet=item.get("snippet", ""),
                        source_type=SourceType.SEARCH_RESULT,
                        raw={
                            "query": query,
                            "domain": urlparse(url).netloc,
                            "position": item.get("position"),
                        },
                    ))

        return findings

    async def _run_query(self, client: httpx.AsyncClient, query: str) -> list[dict]:
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.config["SERPAPI_KEY"],
            "num": 20,
        }
        try:
            r = await client.get(self.BASE_URL, params=params)
            r.raise_for_status()
            return r.json().get("organic_results", []) or []
        except (httpx.HTTPError, ValueError):
            return []
