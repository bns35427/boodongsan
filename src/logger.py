from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


RESULT_COLUMNS = (
    "processed_at",
    "source_row",
    "status",
    "mode",
    "title",
    "address",
    "current_url",
    "error_message",
    "screenshot_path",
)


@dataclass(frozen=True)
class ResultRecord:
    source_row: int
    status: str
    mode: str
    title: str
    address: str
    current_url: str = ""
    error_message: str = ""
    screenshot_path: str = ""
    processed_at: str = ""


class ResultLogger:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: ResultRecord) -> None:
        values = asdict(record)
        values["processed_at"] = record.processed_at or datetime.now().isoformat(
            timespec="seconds"
        )
        is_new = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=RESULT_COLUMNS)
            if is_new:
                writer.writeheader()
            writer.writerow(values)
