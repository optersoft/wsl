"""Download the rootfs image, with a progress bar and an on-disk cache.

Port of `box_core::download` / `box_core::cached`.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from .paths import state_dir


def download(url: str, path: Path) -> None:
    """Download `url` to `path` with a progress bar, overwriting any existing file.

    Writes to a `.part` sibling first so an interrupted transfer never leaves a
    truncated file that the cache would happily reuse.
    """
    partial = path.with_name(path.name + ".part")
    columns = (
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    )
    with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0)) or None
        with Progress(*columns) as progress, partial.open("wb") as file:
            task = progress.add_task(path.name, total=total)
            for chunk in response.iter_bytes():
                file.write(chunk)
                progress.update(task, advance=len(chunk))
    partial.replace(path)


def cached(name: str, url: str) -> Path:
    """Ensure `name` exists under the cache dir, downloading it from `url` if missing."""
    path = state_dir("cache") / name
    if not path.is_file():
        download(url, path)
    return path
