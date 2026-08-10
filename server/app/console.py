"""Startup progress for a human watching a terminal. Presentation only.

The conventions here are the usual ones (clig.dev): status goes to stderr so
piping stdout stays clean, colour reaches an interactive terminal and nowhere
else, and NO_COLOR or TERM=dumb turn it off. Redirected output degrades to
plain ASCII on its own line, which is what a log file or CI wants.

Deliberately no progress bars and no transient lines: the decoder checkpoint
is a single torch.load with no way to report a fraction, and this process
shares stderr with libraries that log whenever they please, so anything not
yet terminated by a newline is liable to be written over.
"""

import os
import sys
import time
from contextlib import contextmanager

_LABEL_WIDTH = 30

# Everything below reads sys.stderr through this rather than binding it at
# import: pytest swaps the stream out after the app is imported, and a module
# holding the original writes straight past the capture.
def _out():
    return sys.stderr


def _colour() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return _out().isatty()


def _glyph(preferred: str, fallback: str) -> str:
    # Attached to a console this encodes as UTF-8, but redirected to a file it
    # falls back to the locale codec — cp1252 on Windows, where a tick raises.
    try:
        preferred.encode(_out().encoding or "ascii")
        return preferred
    except (UnicodeEncodeError, LookupError):
        return fallback


def _paint(code: str, text: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m" if _colour() else text


def _line(marker: str, colour: str, label: str, trailer: str = "") -> None:
    body = f"{label.ljust(_LABEL_WIDTH)}{_paint('2', trailer)}" if trailer else label
    _out().write(f"  {_paint(colour, marker)} {body}\n")
    _out().flush()


@contextmanager
def loading(label: str, *, enabled: bool = True):
    """Time a slow startup step and report it once, after the fact.

    Nothing is written while the step runs. A pending line overwritten by the
    result would be tidier, but it assumes this process owns the stream, and
    it does not — the libraries being waited on log into the same stderr, and
    the first one to do so lands on top of the half-written line. One line
    written after the step is the only version that cannot be corrupted by
    output this module does not control.
    """
    if not enabled:
        yield
        return

    started = time.perf_counter()
    try:
        yield
    except BaseException:
        _line(_glyph("✘", "x"), "31", label, "failed")
        raise
    _line(_glyph("✔", "+"), "32", label, f"{time.perf_counter() - started:.1f}s")


def ready(label: str) -> None:
    """Close the startup block — uvicorn's own 'startup complete' is hidden
    at the log level `npm run dev` runs it with."""
    _line(_glyph("✔", "+"), "32", label)
    _out().write("\n")
    _out().flush()
