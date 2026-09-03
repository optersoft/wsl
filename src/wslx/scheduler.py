r"""Running something in a distribution on a schedule.

A WSL machine is not a server: nothing in it is running when you are not
looking at it, because the whole distribution is stopped. Anything that has to
happen on its own — a nightly backup of a project directory, an `apt update`
before class, a container brought up at logon — has to be started from the
Windows side, and Windows already has the thing that does that.

So this is Task Scheduler, with the command filled in. Every task wslx makes
lives in the `\wslx\` folder, which is what makes it possible to list them,
change them and delete them again without touching anybody else's tasks.

Tasks are created for the current user and at ordinary privilege, so no UAC
prompt: a task that runs `wsl.exe` needs nothing more than the user who can
already run `wsl.exe`.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from . import report, wsl
from .run import run
from .wsl import WslError

#: Task Scheduler folder for everything wslx creates.
FOLDER = "\\wslx"

#: The schedules schtasks understands that make sense for a WSL machine.
SCHEDULES = ("ONCE", "MINUTE", "HOURLY", "DAILY", "WEEKLY", "ONSTART", "ONLOGON")

_LABEL = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class Task:
    """One scheduled task in the wslx folder."""

    label: str
    command: str
    schedule: str
    next_run: str
    status: str

    @property
    def name(self) -> str:
        return f"{FOLDER}\\{self.label}"


def label(value: str) -> str:
    """Validate a task label.

    It becomes part of a task name, so it is kept to the characters that mean
    nothing to Task Scheduler's path syntax — no backslashes, no quotes.
    """
    value = value.strip()
    if not _LABEL.match(value):
        raise WslError(f"{value}: a task name may only hold letters, digits, dot, dash, underscore")
    return value


def parse_tasks(output: str) -> list[Task]:
    """Read `schtasks /Query /FO CSV /V`, keeping only the wslx folder.

    The column *headings* are localised, but their order is not, and neither
    are the task names — so the folder prefix identifies our rows and the
    header row is identified by its first cell repeating the task-name column.
    """
    tasks = []
    for row in csv.reader(io.StringIO(output)):
        if len(row) < 9 or not row[1].startswith(FOLDER + "\\"):
            continue
        name, next_run, status = row[1], row[2], row[3]
        # /V puts the command in "Task To Run" and the trigger in "Schedule
        # Type"; both sit at fixed offsets from the start of the verbose row.
        command = row[8] if len(row) > 8 else ""
        schedule = next((cell for cell in row if cell.upper() in SCHEDULES), "")
        tasks.append(
            Task(
                label=name.split("\\")[-1],
                command=command,
                schedule=schedule,
                next_run=next_run,
                status=status,
            )
        )
    return tasks


def tasks() -> list[Task]:
    """Every task wslx has scheduled."""
    wsl._require_windows()
    result = run(["schtasks", "/Query", "/FO", "CSV", "/V"])
    # An empty folder makes schtasks exit non-zero with "no tasks", which is
    # not an error to report — it is an empty list.
    return parse_tasks(result.out) if result.out else []


def command_for(name: str, command: str, *, user: str = wsl.BOX_USER) -> str:
    """The Windows command line that runs `command` inside `name`.

    `--cd ~` so a relative path in the command means what it would mean in a
    shell there, and `-u` so a task does not silently run as root just because
    DefaultUid says so.
    """
    import subprocess  # noqa: PLC0415 - only for its Windows quoting rules

    return subprocess.list2cmdline(
        ["wsl.exe", "-d", name, "-u", user, "--cd", "~", "--", "sh", "-lc", command]
    )


def create(
    task: str,
    name: str,
    command: str,
    *,
    schedule: str = "DAILY",
    at: str | None = None,
    modifier: str | None = None,
    user: str = wsl.BOX_USER,
) -> Task:
    """Schedule `command` to run inside the distribution `name`.

    `at` is a 24-hour `HH:MM`, required by every time-based schedule and
    meaningless for `ONSTART` and `ONLOGON`. `modifier` is schtasks' `/MO` —
    every N minutes, every N days — and is left alone when it is None.
    """
    wsl._require_windows()
    task = label(task)
    schedule = schedule.upper()
    if schedule not in SCHEDULES:
        raise WslError(f"{schedule}: not one of {', '.join(SCHEDULES)}")
    if not wsl.registered(name):
        raise WslError(f"{name}: not registered")
    if at and not re.match(r"^\d{2}:\d{2}$", at):
        raise WslError(f"{at}: a start time is HH:MM")

    argv = [
        "schtasks",
        "/Create",
        "/TN",
        f"{FOLDER}\\{task}",
        "/TR",
        command_for(name, command, user=user),
        "/SC",
        schedule,
        "/F",
    ]
    if at:
        argv += ["/ST", at]
    if modifier:
        argv += ["/MO", str(modifier)]

    result = run(argv)
    if not result.ok:
        raise WslError(f"{task}: could not be scheduled — {result.message}")
    report.say(f"{task}: scheduled ({schedule.lower()}{' at ' + at if at else ''})")
    fallback = Task(task, command, schedule, "", "Ready")
    return next((found for found in tasks() if found.label == task), fallback)


def delete(task: str) -> None:
    """Remove a scheduled task."""
    wsl._require_windows()
    result = run(["schtasks", "/Delete", "/TN", f"{FOLDER}\\{label(task)}", "/F"])
    if not result.ok:
        raise WslError(f"{task}: could not be deleted — {result.message}")
    report.say(f"{task}: deleted")


def run_now(task: str) -> None:
    """Run a scheduled task immediately, without waiting for its trigger."""
    wsl._require_windows()
    result = run(["schtasks", "/Run", "/TN", f"{FOLDER}\\{label(task)}"])
    if not result.ok:
        raise WslError(f"{task}: could not be run — {result.message}")
    report.say(f"{task}: started")


def enable(task: str, enabled: bool = True) -> None:
    """Turn a task on or off, keeping its definition."""
    wsl._require_windows()
    flag = "/ENABLE" if enabled else "/DISABLE"
    result = run(["schtasks", "/Change", "/TN", f"{FOLDER}\\{label(task)}", flag])
    if not result.ok:
        raise WslError(f"{task}: could not be changed — {result.message}")
    report.say(f"{task}: {'enabled' if enabled else 'disabled'}")
