import asyncio
from datetime import datetime, timezone
from typing import Iterable

from rich.console import Console
from rich.markup import escape

from .investigator import Investigator
from .models import InvestigationResult, Target
from .sanitize import terminal_safe


class Runner:
    """Runs all applicable investigators concurrently against one target."""

    def __init__(
        self,
        investigators: Iterable[Investigator],
        console: Console | None = None,
    ):
        self.investigators = list(investigators)
        self.console = console or Console()

    async def run(self, target: Target) -> InvestigationResult:
        result = InvestigationResult(target=target)
        applicable = [i for i in self.investigators if i.supports(target)]

        if not applicable:
            self.console.print(
                f"[yellow]No investigators support target type: {target.type.value}[/yellow]"
            )
            return result

        async def run_one(inv: Investigator) -> None:
            try:
                findings = await inv.investigate(target)
                for f in findings:
                    result.add_finding(f)
                self.console.print(
                    f"  [green]ok[/green]  {inv.name}: {len(findings)} findings"
                )
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                result.add_error(inv.name, msg)
                self.console.print(
                    f"  [red]err[/red] {inv.name}: {escape(terminal_safe(msg))}"
                )

        await asyncio.gather(*[run_one(inv) for inv in applicable])

        result.completed_at = datetime.now(timezone.utc)
        return result
