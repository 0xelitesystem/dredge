"""Make untrusted text safe to print to a terminal."""

import re

# C0 controls other than tab and newline, DEL, C1 controls, and Unicode
# bidirectional controls that can reorder or hide what is displayed.
_TERMINAL_UNSAFE = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]"
)


def _visible(match: re.Match) -> str:
    cp = ord(match.group())
    return f"\\x{cp:02x}" if cp < 0x100 else f"\\u{cp:04x}"


def terminal_safe(text: str) -> str:
    """Replace terminal control characters with visible escapes like \\x1b."""
    return _TERMINAL_UNSAFE.sub(_visible, text)
