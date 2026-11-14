import asyncio
import json
import ntpath
import os
import re
import stat
import tempfile
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markup import escape

from .core.models import Target, TargetType
from .core.runner import Runner
from .core.sanitize import terminal_safe
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


# Windows maps these names to a device in every folder, whatever the case and
# even with an extension or trailing spaces, so NUL, nul.md and "con " all are.
_WINDOWS_DEVICE_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"]
    + [port + n for port in ("COM", "LPT") for n in "0123456789\u00b9\u00b2\u00b3"]
)

# POSIX names for a stream the process already has open. If that stream is
# redirected to a regular file, swapping a new file in would cut it off.
_OPEN_STREAM_PATH = re.compile(
    r"/dev/(?:stdin|stdout|stderr|fd/\d+)|/proc/(?:self|thread-self|\d+)/fd/\d+"
)


def _is_windows_device_name(path: str) -> bool:
    r"""True when Windows reads `path` as a device: a reserved name such as NUL
    or COM1, or anything in the \\.\ device namespace (\\.\pipe\x and so on)."""
    path = path.replace("/", "\\")
    if path.startswith("\\\\.\\"):
        return True
    stem = ntpath.basename(path).split(".", 1)[0].split(":", 1)[0].rstrip(" ")
    return stem.upper() in _WINDOWS_DEVICE_NAMES


def _is_open_stream_path(path: str) -> bool:
    """True for an absolute POSIX path such as /dev/stdout or /proc/self/fd/1."""
    return _OPEN_STREAM_PATH.fullmatch("/" + path.lstrip("/")) is not None


def _must_write_in_place(path: Path) -> bool:
    """True when `path` is a device or stream rather than a regular file.

    That covers NUL, CON and COM1 on Windows, /dev/stdout and /dev/fd/N on
    POSIX, and anything that already exists but is not a regular file (a
    character device such as /dev/null, a named pipe, a socket, a folder).
    A path that does not exist yet becomes a new regular file.
    """
    if os.name == "nt":
        if _is_windows_device_name(str(path)):
            return True
    elif _is_open_stream_path(os.path.abspath(path)):
        return True
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    return not stat.S_ISREG(mode)


def _write_text(path: Path, text: str) -> None:
    """Write text as UTF-8 via a temp file in the same folder, then swap it in.

    If encoding or writing fails, the temp file is removed and any existing
    file at `path` is left exactly as it was.

    A device or stream (NUL, /dev/null, /dev/stdout, a named pipe) cannot be
    swapped out, so it is opened and written in place, still as UTF-8. The
    text is encoded first, so an encoding error writes nothing to it either.
    """
    if _must_write_in_place(path):
        text.encode("utf-8")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return

    dest = Path(os.path.realpath(path))
    fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        if os.name == "posix":
            try:
                mode = stat.S_IMODE(os.stat(dest).st_mode)
            except FileNotFoundError:
                umask = os.umask(0)
                os.umask(umask)
                mode = 0o666 & ~umask
            os.chmod(tmp, mode)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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
    write_failed = False

    if output:
        try:
            _write_text(output, report)
            console.print(f"markdown -> {output}")
        except UnicodeEncodeError:
            write_failed = True
            console.print(
                f"[red]not written[/red] {escape(str(output))}: the report contains "
                "text that cannot be encoded as UTF-8; any existing file was left unchanged."
            )
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
        _write_text(json_output, json.dumps(payload, indent=2))
        console.print(f"json     -> {json_output}")

    if not output and not json_output:
        console.print()
        # Finding text comes from the target: print it literally, never as markup.
        console.print(terminal_safe(report), markup=False, emoji=False)

    if write_failed:
        raise typer.Exit(1)


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


def deprecated_main():
    """The old `dredge` command. Kept for one release, then removed."""
    import sys as _sys
    print("`dredge` is now `siltscan`. The old command goes away in the next release.", file=_sys.stderr)
    return main()


if __name__ == "__main__":
    main()
