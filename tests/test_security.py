"""Regression tests for report, terminal and file-output safety.

No network access: every finding comes from an in-process fake investigator.
Run from project root: python -m pytest tests/
"""
import asyncio
import io
import json
import os
import shutil
import stat
import subprocess
import threading
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from siltscan import cli
from siltscan.core.investigator import Investigator
from siltscan.core.models import Finding, InvestigationResult, SourceType, Target, TargetType
from siltscan.core.runner import Runner
from siltscan.reporters.markdown import render

REPO_ROOT = Path(__file__).resolve().parent.parent

TRACKED_PATH = "https://acme.example/![a](https://tracker.example/p.png)"


def _finding(title, url="https://acme.example/", snippet="", source=SourceType.SEARCH_RESULT):
    return Finding(
        investigator="fake",
        title=title,
        url=url,
        snippet=snippet,
        source_type=source,
    )


def _fake(findings=(), error=None):
    class Fake(Investigator):
        name = "fake"
        description = "Returns fixed findings for tests."
        requires_keys = []
        supports_types = ["person", "company", "domain"]

        async def investigate(self, target):
            if error is not None:
                raise error
            return list(findings)

    return Fake


def _invoke(monkeypatch, findings, args, console):
    monkeypatch.setitem(cli.REGISTRY, "fake", _fake(findings))
    monkeypatch.setattr(cli, "console", console)
    return CliRunner().invoke(
        cli.app,
        ["investigate", "Acme Corp", "--type", "company", "--modules", "fake", *args],
    )


# dredge-1: target-controlled text must not become live Markdown or HTML.

def _injection_report():
    result = InvestigationResult(Target("Acme", TargetType.COMPANY))
    result.add_finding(_finding(
        "Archived: " + TRACKED_PATH,
        url="https://web.archive.org/web/20200101000000/" + TRACKED_PATH,
        snippet="Snapshot",
        source=SourceType.ARCHIVED_PAGE,
    ))
    result.add_finding(_finding(
        '<img src="https://tracker.example/q.png">',
        snippet="![s](https://tracker.example/s.png)",
    ))
    result.add_finding(_finding("Autolink", snippet="<https://tracker.example/a.png>"))
    return render(result)


def test_report_has_no_live_image_or_html():
    lines = _injection_report().splitlines()
    assert not any("<img" in line or "<https://" in line for line in lines)
    assert '### [&lt;img src="https://tracker.example/q.png">](https://acme.example/)' in lines
    assert "!\\[s\\](https://tracker.example/s.png)" in lines
    assert "&lt;https://tracker.example/a.png>" in lines


def test_report_link_destination_cannot_be_broken_out_of():
    lines = _injection_report().splitlines()
    # Brackets in the title are escaped, and every parenthesis in the URL is
    # escaped, so the whole archive URL is one link destination.
    assert (
        "### [Archived: https://acme.example/!\\[a\\](https://tracker.example/p.png)]"
        "(https://web.archive.org/web/20200101000000/https://acme.example/"
        "![a]\\(https://tracker.example/p.png\\))"
    ) in lines


def test_report_renders_injection_as_text_when_markdown_it_is_available():
    try:
        from markdown_it import MarkdownIt
    except ImportError:
        pytest.skip("markdown-it-py not installed")
    html = MarkdownIt("commonmark").render(_injection_report())
    assert "<img" not in html
    assert 'href="https://tracker.example' not in html


def test_report_untrusted_text_cannot_start_new_blocks():
    result = InvestigationResult(Target("Acme", TargetType.COMPANY))
    result.add_finding(_finding(
        "Line one\n# Forged heading",
        snippet="## Acme cleared\n- forged finding\r\n[x]: https://tracker.example/r.png",
    ))
    result.add_finding(_finding("Other", snippet="# Forged at line start"))
    result.add_error("fake", "boom\n## Forged section")
    md = render(result)
    forged = ("# Forged", "## Acme", "- forged", "[x]:", "## Forged")
    assert not any(line.startswith(forged) for line in md.splitlines())


def test_report_keeps_bare_mark_tags_only():
    result = InvestigationResult(Target("Acme", TargetType.COMPANY))
    result.add_finding(_finding("Hit", snippet="Acme <mark>fraud</mark> <mark style=x>y</mark> &lt;b&gt;"))
    md = render(result)
    assert "Acme <mark>fraud</mark> &lt;mark style=x>y</mark> &amp;lt;b&amp;gt;\n" in md


def test_report_does_not_link_non_http_urls():
    result = InvestigationResult(Target("Acme", TargetType.COMPANY))
    result.add_finding(_finding("Click me", url="javascript:alert(1)"))
    md = render(result)
    assert "javascript:" not in md
    assert "### Click me" in md


def test_report_normal_findings_unchanged():
    result = InvestigationResult(Target("Example Target", TargetType.PERSON, ["E. Target"], ["example.com"]))
    result.add_finding(_finding(
        "Example Target v. State of California",
        url="https://www.courtlistener.com/docket/example/",
        snippet="Civil action filed 2019. Settled 2021 for undisclosed sum.",
        source=SourceType.COURT_RECORD,
    ))
    result.add_finding(_finding(
        "r/scams - Anyone else lose money to Example Target?",
        url="https://reddit.com/r/scams/comments/example",
        snippet="Thread with 234 comments documenting alleged misconduct.",
    ))
    for title in (
        "Acme Corp Reviews | Read Customer Service Reviews",
        "AT&T and Smith & Wesson Q&A",
        "Archived: https://example.com/about_us/team_page",
        "Home > Products > Acme 2*3 ~ approx",
    ):
        result.add_finding(_finding(title, url="https://example.org/" + str(len(title))))
    md = render(result)
    for title in (
        "Acme Corp Reviews | Read Customer Service Reviews",
        "AT&T and Smith & Wesson Q&A",
        "Archived: https://example.com/about_us/team_page",
        "Home > Products > Acme 2*3 ~ approx",
    ):
        assert f"### [{title}](https://example.org/{len(title)})\n" in md
    assert "# Investigation: Example Target\n" in md
    assert "- Aliases: E. Target\n" in md
    assert "- Known domains: example.com\n" in md
    assert "### [Example Target v. State of California](https://www.courtlistener.com/docket/example/)\n" in md
    assert "Civil action filed 2019. Settled 2021 for undisclosed sum.\n" in md
    assert "### [r/scams - Anyone else lose money to Example Target?](https://reddit.com/r/scams/comments/example)\n" in md


# dredge-2: finding text printed to the terminal must not be read as Rich markup
# or reach the terminal as control sequences.

HOSTILE_TITLES = [
    "Acme Corp careers [conceal]",
    "Acme Corp sued for fraud",
    "Acme review [/x] closing tag",
    "Escape \x1b[8mhidden\x1b[0m and \x1b]0;title\x07 bidi \u202eevil\u202c",
]


def test_cli_default_output_is_literal_text(monkeypatch):
    buf = io.StringIO()
    console = Console(file=buf, width=300, color_system=None)
    res = _invoke(monkeypatch, [_finding(t) for t in HOSTILE_TITLES], [], console)
    out = buf.getvalue()
    assert res.exit_code == 0, res.exception
    # Titles appear as their (Markdown-escaped) text instead of being eaten as tags.
    assert "Acme Corp careers \\[conceal\\]" in out
    assert "Acme review \\[/x\\] closing tag" in out
    assert "Acme Corp sued for fraud" in out
    assert "\x1b" not in out
    assert "\x07" not in out
    assert "\u202e" not in out
    assert "Escape \\x1b\\[8mhidden" in out
    assert "bidi \\u202eevil\\u202c" in out


def test_cli_default_output_cannot_conceal_later_findings(monkeypatch):
    buf = io.StringIO()
    console = Console(file=buf, width=300, force_terminal=True, color_system="standard", legacy_windows=False)
    findings = [_finding(HOSTILE_TITLES[0]), _finding(HOSTILE_TITLES[1], snippet="Class action filed")]
    res = _invoke(monkeypatch, findings, [], console)
    assert res.exit_code == 0, res.exception
    assert "\x1b[8m" not in buf.getvalue()


def test_runner_error_text_is_literal():
    buf = io.StringIO()
    console = Console(file=buf, width=300, color_system=None)
    err = RuntimeError("upstream said [/x] then \x1b]0;pwned\x07")
    runner = Runner([_fake(error=err)({})], console=console)
    result = asyncio.run(runner.run(Target("Acme", TargetType.COMPANY)))
    out = buf.getvalue()
    assert "[/x]" in out
    assert "\x1b" not in out
    assert "\x07" not in out
    assert result.errors


# dredge-3: report files are UTF-8, and a failed write never destroys the old file.

def test_cli_writes_utf8_report_and_json(monkeypatch, tmp_path):
    title = "\u682a\u5f0f\u4f1a\u793e \u2192 \u0141ukasz \U0001f680"
    report = tmp_path / "report.md"
    report.write_bytes(b"PRIOR REPORT")
    findings_json = tmp_path / "findings.json"
    res = _invoke(
        monkeypatch, [_finding(title)],
        ["-o", str(report), "--json", str(findings_json)],
        Console(file=io.StringIO(), width=300),
    )
    assert res.exit_code == 0, res.exception
    assert title in report.read_bytes().decode("utf-8")
    assert json.loads(findings_json.read_text(encoding="utf-8"))["findings"][0]["title"] == title
    assert sorted(p.name for p in tmp_path.iterdir()) == ["findings.json", "report.md"]


def test_cli_unencodable_report_leaves_existing_file_untouched(monkeypatch, tmp_path):
    report = tmp_path / "report.md"
    report.write_bytes(b"PRIOR REPORT")
    findings_json = tmp_path / "findings.json"
    res = _invoke(
        monkeypatch, [_finding("lone surrogate \ud800 from a JSON API")],
        ["-o", str(report), "--json", str(findings_json)],
        Console(file=io.StringIO(), width=300),
    )
    assert res.exit_code == 1
    assert report.read_bytes() == b"PRIOR REPORT"
    assert findings_json.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["findings.json", "report.md"]


# dredge-3 follow-up: a device or stream cannot be swapped out for a new file,
# so it is written in place. Regular files keep the atomic temp-and-replace.

def test_cli_writes_report_and_json_to_the_null_device(monkeypatch, tmp_path):
    # os.devnull is "nul" on Windows and "/dev/null" on POSIX.
    monkeypatch.chdir(tmp_path)
    buf = io.StringIO()
    res = _invoke(
        monkeypatch, [_finding("Acme Corp caf\u00e9")],
        ["-o", os.devnull, "--json", os.devnull],
        Console(file=buf, width=300),
    )
    assert res.exit_code == 0, res.exception
    assert f"markdown -> {os.devnull}" in buf.getvalue()
    assert f"json     -> {os.devnull}" in buf.getvalue()
    assert list(tmp_path.iterdir()) == []


def test_cli_unencodable_report_to_the_null_device_is_reported(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    buf = io.StringIO()
    res = _invoke(
        monkeypatch, [_finding("lone surrogate \ud800 from a JSON API")],
        ["-o", os.devnull],
        Console(file=buf, width=300),
    )
    assert res.exit_code == 1
    assert "not written" in buf.getvalue()
    assert list(tmp_path.iterdir()) == []


def test_write_text_still_swaps_a_new_file_in_for_a_regular_file(tmp_path):
    report = tmp_path / "report.md"
    report.write_bytes(b"PRIOR REPORT")
    try:
        os.link(report, tmp_path / "prior.md")
    except (OSError, NotImplementedError):
        pytest.skip("hard links are not supported here")
    cli._write_text(report, "caf\u00e9\n")
    # The hard link still holds the old bytes: the file was replaced, not rewritten.
    assert (tmp_path / "prior.md").read_bytes() == b"PRIOR REPORT"
    assert report.read_bytes() == ("caf\u00e9" + os.linesep).encode("utf-8")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["prior.md", "report.md"]


def test_only_regular_files_and_new_paths_get_the_atomic_write(tmp_path):
    existing = tmp_path / "report.md"
    existing.write_bytes(b"PRIOR REPORT")
    assert not cli._must_write_in_place(existing)
    assert not cli._must_write_in_place(tmp_path / "new-report.md")
    assert cli._must_write_in_place(Path(os.devnull))
    assert cli._must_write_in_place(tmp_path)  # a folder is not a regular file either
    # NUL names a device only on Windows; elsewhere it is an ordinary file name.
    assert cli._must_write_in_place(tmp_path / "NUL") is (os.name == "nt")


@pytest.mark.parametrize("name", [
    "NUL", "nul", "Nul.md", "nul.tar.gz", "NUL ", "NUL.", "NUL:", "con", "PRN.txt", "aux",
    "COM1", "com9.log", "LPT0", "COM\u00b9", "lpt\u00b3.md", "CONIN$", "conout$",
    "C:\\reports\\NUL", "C:NUL", "reports/nul.md",
    "\\\\.\\NUL", "\\\\.\\COM12", "\\\\.\\pipe\\siltscan", "//./pipe/siltscan",
])
def test_windows_device_names_are_recognized(name):
    assert cli._is_windows_device_name(name)


@pytest.mark.parametrize("name", [
    "report.md", "null", "NULL.md", "nul_report.md", "my-nul.md", "console", "CONSOLE.md",
    "COM10", "LPT", "COMA", "AUXILIARY.txt", "C:\\NUL\\report.md", "reports/con/findings.json",
    "C:\\", "",
])
def test_ordinary_windows_names_are_not_devices(name):
    assert not cli._is_windows_device_name(name)


@pytest.mark.parametrize("path, expected", [
    ("/dev/stdout", True), ("/dev/stderr", True), ("/dev/stdin", True),
    ("/dev/fd/1", True), ("/dev/fd/42", True), ("//dev/stdout", True),
    ("/proc/self/fd/1", True), ("/proc/thread-self/fd/2", True), ("/proc/1234/fd/7", True),
    # /dev/null is a character device, so its file type catches it instead.
    ("/dev/null", False), ("/dev/shm/report.md", False), ("/home/u/dev/stdout", False),
    ("/dev/fd/x", False), ("/dev/stdout/x", False), ("/proc/self/fd", False), ("/tmp/report.md", False),
])
def test_open_stream_paths_are_recognized(path, expected):
    assert cli._is_open_stream_path(path) is expected


needs_fifo = pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs POSIX named pipes")


@needs_fifo
def test_write_text_streams_into_a_named_pipe(tmp_path):
    fifo = tmp_path / "report.pipe"
    os.mkfifo(fifo)
    received = []
    reader = threading.Thread(target=lambda: received.append(fifo.read_bytes()), daemon=True)
    reader.start()
    cli._write_text(fifo, "caf\u00e9\n")
    reader.join(10)
    assert received == ["caf\u00e9\n".encode("utf-8")]
    assert stat.S_ISFIFO(os.stat(fifo).st_mode)
    assert [p.name for p in tmp_path.iterdir()] == ["report.pipe"]


@needs_fifo
def test_write_text_rejects_unencodable_text_before_opening_a_pipe(tmp_path):
    # Opening a pipe for writing blocks until a reader arrives, and none will.
    fifo = tmp_path / "report.pipe"
    os.mkfifo(fifo)
    raised = []

    def write():
        try:
            cli._write_text(fifo, "lone surrogate \ud800")
        except UnicodeEncodeError as exc:
            raised.append(exc)

    writer = threading.Thread(target=write, daemon=True)
    writer.start()
    writer.join(10)
    assert raised and not writer.is_alive()


@pytest.mark.skipif(os.name != "posix" or not os.path.isdir("/dev/fd"), reason="needs /dev/fd")
def test_write_text_writes_through_a_dev_fd_path():
    # /dev/stdout is /dev/fd/1. A pipe of our own stands in for a redirected
    # stdout, so pytest's captured output is left alone.
    r, w = os.pipe()
    try:
        cli._write_text(Path(f"/dev/fd/{w}"), "caf\u00e9\n")
    finally:
        os.close(w)
    with os.fdopen(r, "rb") as fh:
        assert fh.read() == "caf\u00e9\n".encode("utf-8")


# dredge-4: the key file and venv the README creates in the clone are git-ignored.

def _git_ignored(path):
    return subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=REPO_ROOT, capture_output=True,
    ).returncode == 0


def test_gitignore_covers_env_and_venv():
    if not shutil.which("git") or not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    for path in (".env", ".env.local", ".venv/pyvenv.cfg", "siltscan/__pycache__/cli.cpython-312.pyc"):
        assert _git_ignored(path), path
    assert not _git_ignored(".env.example")
    assert (REPO_ROOT / ".env.example").is_file()
