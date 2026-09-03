"""Where progress messages go.

The core modules are driven by two front ends: the CLI, where a message is a
line on stdout, and the GUI, where it is a row in a log pane and must never
touch a console that may not exist. So nothing below `cli.py` prints — it calls
:func:`say`, and whoever is driving decides what that means.

The default sink writes to stdout, so a core function called from a script or a
test behaves exactly as it did when the printing was inline — including the
half-written "starting ..." line that a later call completes with " done.",
which is what `end` is for and why a sink takes it.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager

#: A sink receives the message and the line ending the caller asked for.
Sink = Callable[[str, str], None]


def _stdout(message: str, end: str) -> None:
    sys.stdout.write(message + end)
    sys.stdout.flush()


_sink: Sink = _stdout


def say(message: str, end: str = "\n") -> None:
    """Report progress to whoever is driving."""
    _sink(message, end)


@contextmanager
def sink(target: Sink) -> Iterator[None]:
    """Route :func:`say` to `target` for the duration of the block."""
    global _sink
    previous = _sink
    _sink = target
    try:
        yield
    finally:
        _sink = previous
