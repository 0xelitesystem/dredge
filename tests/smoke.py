"""Smoke test: synthesize findings, render a report.

Validates that all components compose without network access.
Run from project root: python tests/smoke.py
"""
import asyncio
from datetime import datetime, timedelta, timezone

from dredge.core.investigator import Investigator
from dredge.core.keywords import build_queries
from dredge.core.models import Finding, InvestigationResult, SourceType, Target, TargetType
from dredge.core.runner import Runner
from dredge.reporters.markdown import render


class FakeInvestigator(Investigator):
    name = "fake"
    description = "Synthetic findings for testing."
    requires_keys = []
    supports_types = ["person", "company"]

    async def investigate(self, target):
        now = datetime.now(timezone.utc)
        return [
            Finding(
                investigator=self.name,
                title=f"{target.name} v. State of California",
                url="https://www.courtlistener.com/docket/example/",
                snippet="Civil action filed 2019. Settled 2021 for undisclosed sum.",
                source_type=SourceType.COURT_RECORD,
                timestamp=now - timedelta(days=600),
            ),
            Finding(
                investigator=self.name,
                title=f"Likely deleted: example.com/about/{target.name.lower()}",
                url="https://web.archive.org/web/20210101/example.com/about",
                snippet="Page was last archived alive on 2021-01-01, later returned HTTP 404 on 2023-05-15.",
                source_type=SourceType.DELETED_CONTENT,
                timestamp=now - timedelta(days=900),
            ),
            Finding(
                investigator=self.name,
                title=f"r/scams - Anyone else lose money to {target.name}?",
                url="https://reddit.com/r/scams/comments/example",
                snippet="Thread with 234 comments documenting alleged misconduct.",
                source_type=SourceType.SEARCH_RESULT,
                timestamp=now - timedelta(days=120),
            ),
        ]


async def _main():
    target = Target(
        name="Example Target",
        type=TargetType.PERSON,
        aliases=["E. Target"],
        known_domains=["example.com"],
    )
    runner = Runner([FakeInvestigator({})])
    result = await runner.run(target)
    print(render(result))


def test_build_queries():
    queries = build_queries(
        "Jane Doe",
        clusters=["fraud", "legal"],
        exclude_domains=["janedoe.com"],
    )
    assert any("janedoe.com" in q for q in queries)
    assert any("scam" in q for q in queries)
    assert any("lawsuit" in q for q in queries)
    assert any("site:reddit.com" in q for q in queries)
    print(f"build_queries: ok ({len(queries)} queries generated)")


def test_target_alias_collation():
    t = Target(name="X", type=TargetType.PERSON, aliases=["Y", "Z"])
    assert t.all_names == ["X", "Y", "Z"]
    print("Target.all_names: ok")


def test_finding_serialization():
    f = Finding(
        investigator="fake",
        title="t", url="u", snippet="s",
        source_type=SourceType.SEARCH_RESULT,
    )
    d = f.to_dict()
    assert d["investigator"] == "fake"
    assert d["source_type"] == "search_result"
    assert d["timestamp"] is None
    print("Finding.to_dict: ok")


def test_investigator_supports():
    inv = FakeInvestigator({})
    assert inv.supports(Target(name="x", type=TargetType.PERSON))
    assert not inv.supports(Target(name="x", type=TargetType.WALLET))
    print("Investigator.supports: ok")


if __name__ == "__main__":
    test_build_queries()
    test_target_alias_collation()
    test_finding_serialization()
    test_investigator_supports()
    print("\n--- rendered report ---\n")
    asyncio.run(_main())
