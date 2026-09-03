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
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, replace

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

    The column *headings* are localised and so are most of the values, but the
    task names are not — so the folder prefix identifies our rows, and only the
    columns whose position is fixed at the start of the row are read from here.

    The schedule is deliberately **not** one of them. On a Spanish Windows the
    "Schedule Type" cell says `Diariamente`, and matching it against a list of
    English words is how a working daily task displays a blank schedule; that
    question is answered from the task's XML instead, which is language
    neutral. Found on a Spanish Windows 10 22H2 desktop, where every task came
    back with an empty column.
    """
    tasks = []
    for row in csv.reader(io.StringIO(output)):
        if len(row) < 9 or not row[1].startswith(FOLDER + "\\"):
            continue
        name, next_run, status = row[1], row[2], row[3]
        tasks.append(
            Task(
                label=name.split("\\")[-1],
                command=row[8],
                schedule="",
                next_run=next_run,
                status=status,
            )
        )
    return tasks


#: What each Task Scheduler trigger element means, in schtasks' own words.
_TRIGGERS = {
    "BootTrigger": "ONSTART",
    "LogonTrigger": "ONLOGON",
    "TimeTrigger": "ONCE",
    "ScheduleByDay": "DAILY",
    "ScheduleByWeek": "WEEKLY",
    "ScheduleByMonth": "MONTHLY",
}


def parse_schedule(xml: str) -> str:
    """Read the trigger out of a task's XML definition.

    Every element here is a Task Scheduler schema name, identical on every
    Windows in every language — which is the whole reason to ask the XML
    rather than read a translated table cell. The namespace is stripped
    because the schema URI has changed between Windows versions.
    """
    try:
        root = ElementTree.fromstring(xml.lstrip("\ufeff"))
    except ElementTree.ParseError:
        return ""
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in _TRIGGERS:
            return _TRIGGERS[tag]
    return ""


def tasks() -> list[Task]:
    """Every task wslx has scheduled, with its trigger."""
    wsl._require_windows()
    result = run(["schtasks", "/Query", "/FO", "CSV", "/V"])
    # An empty folder makes schtasks exit non-zero with "no tasks", which is
    # not an error to report — it is an empty list.
    found = parse_tasks(result.out) if result.out else []
    return [replace(task, schedule=schedule(task.label)) for task in found]


def schedule(task: str) -> str:
    """When a task runs, read from its XML rather than from a translated table."""
    xml = run(["schtasks", "/Query", "/TN", f"{FOLDER}\\{task}", "/XML", "ONE"])
    return parse_schedule(xml.out) if xml.ok else ""


def command_for(name: str, command: str, *, user: str | None = None) -> str:
    """The Windows command line that runs `command` inside `name`.

    `--cd ~` so a relative path in the command means what it would mean in a
    shell there. `-u` is passed only for a machine wslx made, where `box` is
    known to exist: naming it on someone else's Ubuntu schedules a task that
    fails every night with "no such user", and leaving it out lets that
    distribution use whichever user it opens as.
    """
    import subprocess  # noqa: PLC0415 - only for its Windows quoting rules

    argv = ["wsl.exe", "-d", name]
    if user:
        argv += ["-u", user]
    return subprocess.list2cmdline([*argv, "--cd", "~", "--", "sh", "-lc", command])


def create(
    task: str,
    name: str,
    command: str,
    *,
    schedule: str = "DAILY",
    at: str | None = None,
    modifier: str | None = None,
    user: str | None = None,
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
    if user is None and wsl.managed(name):
        user = wsl.BOX_USER

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
