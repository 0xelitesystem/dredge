from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TargetType(str, Enum):
    PERSON = "person"
    COMPANY = "company"
    DOMAIN = "domain"
    WALLET = "wallet"


class SourceType(str, Enum):
    SEARCH_RESULT = "search_result"
    DELETED_CONTENT = "deleted_content"
    ARCHIVED_PAGE = "archived_page"
    COURT_RECORD = "court_record"
    REGULATORY_FILING = "regulatory_filing"
    SOCIAL_MEDIA = "social_media"
    NEWS_ARTICLE = "news_article"
    ON_CHAIN = "on_chain"


@dataclass
class Target:
    name: str
    type: TargetType
    aliases: list[str] = field(default_factory=list)
    known_domains: list[str] = field(default_factory=list)

    @property
    def all_names(self) -> list[str]:
        return [self.name] + self.aliases


@dataclass
class Finding:
    investigator: str
    title: str
    url: str
    snippet: str
    source_type: SourceType
    timestamp: Optional[datetime] = None
    found_at: datetime = field(default_factory=_utcnow)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "investigator": self.investigator,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source_type": self.source_type.value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "found_at": self.found_at.isoformat(),
            "raw": self.raw,
        }


@dataclass
class InvestigationResult:
    target: Target
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None

    def add_finding(self, finding: Finding) -> None:
        self.findings.append(finding)

    def add_error(self, investigator: str, error: str) -> None:
        self.errors.append(f"[{investigator}] {error}")
