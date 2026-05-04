import asyncio
import json
import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

from .core.models import Target, TargetType
from .core.runner import Runner
from .investigators.courtlistener import CourtListenerInvestigator
from .investigators.google_dork import GoogleDorkInvestigator
from .investigators.wayback import WaybackInvestigator
from .reporters.markdown import render as render_markdown


load_dotenv()
app = typer.Typer(add_completion=False, help="Surface what search engines bury.")
console = Console()


REGISTRY: dict[str, type] = {
    "google_dork": GoogleDorkInvestigator,
    "wayback": WaybackInvestigator,
    "courtlistener": CourtListenerInvestigator,
}


def _build(names: list[str], config: dict[str, str]) -> list:
    out = []
    for name in names:
        cls = REGISTRY.get(name)
        if not cls:
            console.print(f"[yellow]Unknown investigator: {name}[/yellow]")
            continue
        try:
            out.append(cls(config))
        except ValueError as e:
            console.print(f"[yellow]Skipping {name}: {e}[/yellow]")
    return out


def _split(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


@app.command()
def investigate(
    name: str = typer.Argument(..., help="Person, company, or domain to investigate."),
    target_type: str = typer.Option(
        "person", "--type", "-t", help="person | company | domain"
    ),
    aliases: str = typer.Option("", "--aliases", help="Comma-separated alternate names."),
    domains: str = typer.Option(
        "", "--domains", help="Comma-separated known domains owned by the target."
    ),
    modules: str = typer.Option(
        "google_dork,wayback,courtlistener",
        "--modules", "-m",
        help="Comma-separated investigator names.",
    ),
    output: Path = typer.Option(None, "--output", "-o", help="Write markdown report to file."),
    json_output: Path = typer.Option(None, "--json", help="Write JSON output to file."),
):
    """Run an investigation against the named target."""
    target = Target(
        name=name,
        type=TargetType(target_type),
        aliases=_split(aliases),
        known_domains=_split(domains),
    )

    config = dict(os.environ)
    investigators = _build(_split(modules), config)

    if not investigators:
        console.print("[red]No investigators available. Check API keys in .env.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]target[/bold]       {target.name} ({target.type.value})")
    console.print(
        f"[bold]running[/bold]      {', '.join(i.name for i in investigators)}"
    )
    console.print()

    runner = Runner(investigators, console=console)
    result = asyncio.run(runner.run(target))

    console.print()
    console.print(
        f"[bold]done[/bold]         {len(result.findings)} findings, {len(result.errors)} errors"
    )

    report = render_markdown(result)

    if output:
        output.write_text(report)
        console.print(f"markdown -> {output}")
    if json_output:
        payload = {
            "target": {
                "name": result.target.name,
                "type": result.target.type.value,
                "aliases": result.target.aliases,
                "known_domains": result.target.known_domains,
            },
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "findings": [f.to_dict() for f in result.findings],
            "errors": result.errors,
        }
        json_output.write_text(json.dumps(payload, indent=2))
        console.print(f"json     -> {json_output}")

    if not output and not json_output:
        console.print()
        console.print(report)


@app.command(name="list-investigators")
def list_investigators():
    """List available investigator modules and their requirements."""
    for name, cls in REGISTRY.items():
        keys = ", ".join(cls.requires_keys) if cls.requires_keys else "none"
        console.print(f"[bold]{name}[/bold]")
        console.print(f"  {cls.description}")
        console.print(f"  required env vars: {keys}")
        console.print(f"  supports: {', '.join(cls.supports_types)}")
        console.print()


def main():
    app()


if __name__ == "__main__":
    main()
