"""Append-only JSONL event journal.

Captures raw WS-in and orders-out so the replay backtester (docs 04 §9) can
reconstruct books and re-run the strategy. Also the substrate for post-mortems.
Cheap: one line per event, flushed, rotated by day.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Journal:
    def __init__(self, directory: str | Path, *, enabled: bool = True, day: str = "live") -> None:
        self.enabled = enabled
        self._fh = None
        if enabled:
            d = Path(directory)
            d.mkdir(parents=True, exist_ok=True)
            self._fh = (d / f"{day}.jsonl").open("a", buffering=1)

    def write(self, kind: str, payload: Any, ts: float) -> None:
        if not self.enabled or self._fh is None:
            return
        self._fh.write(json.dumps({"ts": ts, "kind": kind, "data": payload}, default=str) + "\n")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
