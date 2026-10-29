"""The paths owned by a simulation attempt and the engine's raw-output retention decision.

These records describe ownership only. Backends still choose their execution protocol; the engine still decides
what is kept after a result is durable. Nothing here changes the records written to disk.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import TypedDict
from uuid import uuid4


@dataclass(frozen=True)
class SimulationArtifacts:
    # Paths linking a verified export to one simulation attempt's copied deck and result directory.
    export_path: Path
    result_directory: Path
    deck_path: Path

    @classmethod
    def copy_deck(cls, export_path: Path, work_root: Path) -> SimulationArtifacts:
        """A fresh attempt: keep the verified export and run its copy beside this attempt's raw output and logs."""
        directory = work_root / uuid4().hex
        directory.mkdir(parents=True)
        deck = directory / export_path.name
        shutil.copyfile(export_path, deck)
        return cls(export_path, directory, deck)


class RetentionItem(TypedDict):
    """One committed job's decision; source and export are separate owned paths, target is relative to the run."""
    source: str | None
    record: dict
    decision: str
    target: str | None
    evaluation_id: str
    job_id: str
    journal: str | None
