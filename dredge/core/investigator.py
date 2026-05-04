from abc import ABC, abstractmethod
from typing import Mapping

from .models import Finding, Target


class Investigator(ABC):
    """Base class for all data-source plugins.

    Subclasses set class-level metadata and implement `investigate`.
    The runner instantiates each one with the env-var config dict and
    runs them concurrently against a single target.
    """

    name: str = ""
    description: str = ""
    requires_keys: list[str] = []
    supports_types: list[str] = ["person", "company"]

    def __init__(self, config: Mapping[str, str]):
        self.config = config
        self._validate_keys()

    def _validate_keys(self) -> None:
        missing = [k for k in self.requires_keys if not self.config.get(k)]
        if missing:
            raise ValueError(
                f"{self.name} requires environment variables: {', '.join(missing)}"
            )

    @abstractmethod
    async def investigate(self, target: Target) -> list[Finding]:
        ...

    def supports(self, target: Target) -> bool:
        return target.type.value in self.supports_types
