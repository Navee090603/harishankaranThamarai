from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


@dataclass
class StateStore:
    path: Path
    lock: threading.Lock = field(default_factory=threading.Lock)
    data: dict[str, Any] = field(default_factory=dict)

    def load(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.data = self._new_state()
            self.save()
            return

        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.data = self._new_state()

        self._reset_if_new_day()
        self.save()

    def _new_state(self) -> dict[str, Any]:
        return {
            "business_date": datetime.now(tz=IST).strftime("%Y%m%d"),
            "files": {},
            "sent_alerts": {},
            "step_not_received_sent": {},
        }

    def _reset_if_new_day(self) -> None:
        today = datetime.now(tz=IST).strftime("%Y%m%d")
        if self.data.get("business_date") != today:
            self.data = self._new_state()

    def save(self) -> None:
        with self.lock:
            self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def setdefault(self, key: str, default):
        return self.data.setdefault(key, default)

    def mark_alert(self, key: str) -> bool:
        sent = self.setdefault("sent_alerts", {})
        if sent.get(key):
            return False
        sent[key] = True
        self.save()
        return True
