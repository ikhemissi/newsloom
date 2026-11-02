"""Single-process bounded success payloads, with non-sliding read-start expiry."""

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from newsloom_mcp.http_models import ResultScope


@dataclass(frozen=True)
class Entry:
    payload: bytes
    read_at: datetime
    started: float
    result_scope: ResultScope


class ResponseCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.entries: OrderedDict[str, Entry] = OrderedDict()
        self.bytes = 0

    def _remove(self, key: str) -> None:
        self.bytes -= len(self.entries.pop(key).payload)

    def _expire(self) -> None:
        now = self.clock()
        for key in [key for key, entry in self.entries.items() if now >= entry.started + 60]:
            self._remove(key)

    def get(self, key: str) -> Entry | None:
        self._expire()
        entry = self.entries.get(key)
        if entry is not None:
            self.entries.move_to_end(key)
        return entry

    def put(self, key: str, entry: Entry) -> bool:
        self._expire()
        if len(key) != 64 or len(entry.payload) > 512 * 1024 or self.clock() >= entry.started + 60:
            return False
        if key in self.entries:
            self._remove(key)
        while self.entries and (
            len(self.entries) >= 128 or self.bytes + len(entry.payload) > 8 * 1024 * 1024
        ):
            self._remove(next(iter(self.entries)))
        self.entries[key] = entry
        self.bytes += len(entry.payload)
        return True
