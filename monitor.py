from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import AppConfig, EST, IST, StepConfig
from mailer import Mailer
from state_store import StateStore


@dataclass
class FileSnapshot:
    path: Path
    size: int
    mtime: float


class FileMonitor:
    def __init__(self, config: AppConfig, state: StateStore, mailer: Mailer, logger: logging.Logger):
        self.config = config
        self.state = state
        self.mailer = mailer
        self.logger = logger
        self.stop_event = threading.Event()

    def shutdown(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        self.logger.info("Starting file monitor")
        self._recover_state()

        while not self.stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                self.logger.exception("Unhandled loop error: %s", exc)
            self.stop_event.wait(self.config.poll_interval_seconds)

        self.logger.info("File monitor stopped gracefully")

    def _tick(self) -> None:
        self._daily_rollover_if_needed()

        snapshots: dict[str, dict[str, FileSnapshot]] = {}
        for step in self.config.steps:
            snapshots[step.name] = self._scan_step(step)

        self._process_workflow(snapshots)
        self._send_not_received_alerts(snapshots)
        self.state.save()

    def _daily_rollover_if_needed(self) -> None:
        today = datetime.now(tz=IST).strftime("%Y%m%d")
        if self.state.get("business_date") != today:
            self.logger.info("New IST day detected, resetting state")
            self.state.data = {
                "business_date": today,
                "files": {},
                "sent_alerts": {},
                "step_not_received_sent": {},
            }

    def _recover_state(self) -> None:
        self.logger.info("Running restart recovery")
        # Startup scan to continue within the active window and avoid duplicates
        startup_snapshots = {step.name: self._scan_step(step) for step in self.config.steps}
        self._process_workflow(startup_snapshots)
        self.state.save()

    def _scan_step(self, step: StepConfig) -> dict[str, FileSnapshot]:
        result: dict[str, FileSnapshot] = {}

        if not step.folder.exists():
            self.logger.error("Folder missing for %s: %s", step.name, step.folder)
            return result

        if not step.folder.is_dir():
            self.logger.error("Path not directory for %s: %s", step.name, step.folder)
            return result

        for path in step.folder.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() == ".tmp":
                continue

            try:
                size = path.stat().st_size
                mtime = path.stat().st_mtime
            except OSError as exc:
                self.logger.error("File access issue %s: %s", path, exc)
                continue

            result[path.name] = FileSnapshot(path=path, size=size, mtime=mtime)
        return result

    def _in_window(self, step: StepConfig, now_ist: datetime) -> bool:
        t = now_ist.time().replace(second=0, microsecond=0)
        return step.start_time <= t <= step.end_time

    def _process_workflow(self, snapshots: dict[str, dict[str, FileSnapshot]]) -> None:
        now_ist = datetime.now(tz=IST)
        now_est = now_ist.astimezone(EST)
        date_token = now_ist.strftime("%Y%m%d")

        files_state = self.state.setdefault("files", {})

        step1_names = self._valid_files_in_step(self.config.steps[0], snapshots["Step1"], date_token)
        for name, snap in step1_names.items():
            key = self._file_key(name)
            record = files_state.setdefault(key, self._blank_file_record(key))
            self._mark_arrival(record, "Step1", snap, now_ist, now_est)

        for idx, step in enumerate(self.config.steps[1:], start=1):
            step_snaps = self._valid_files_in_step(step, snapshots[step.name], date_token)
            for name, snap in step_snaps.items():
                key = self._file_key(name)
                record = files_state.setdefault(key, self._blank_file_record(key))

                if idx >= 2 and key not in files_state:
                    self.logger.warning("Out-of-sequence file in %s: %s", step.name, name)

                self._mark_arrival(record, step.name, snap, now_ist, now_est)
                prev_step = self.config.steps[idx - 1].name
                self._mark_moved_if_needed(record, prev_step, step.name, now_ist, now_est)

        self._evaluate_stuck_and_sla(now_ist, now_est)

    def _valid_files_in_step(
        self,
        step: StepConfig,
        snapshots: dict[str, FileSnapshot],
        date_token: str,
    ) -> dict[str, FileSnapshot]:
        valid: dict[str, FileSnapshot] = {}
        for name, snap in snapshots.items():
            if snap.path.suffix.lower() != step.extension:
                self.logger.warning("Wrong extension in %s: %s", step.name, name)
                continue
            if date_token not in name:
                self.logger.warning("Wrong date token in %s: %s", step.name, name)
                continue
            if snap.size <= 0:
                self.logger.warning("Zero-byte file in %s: %s", step.name, name)
                continue
            if not self._is_stable(snap.path, snap.size):
                self.logger.info("File still growing in %s: %s", step.name, name)
                continue
            valid[name] = snap
        if len(valid) > step.expected_count:
            self.logger.warning("More than expected files in %s (expected=%s found=%s)", step.name, step.expected_count, len(valid))
        return valid

    def _is_stable(self, path: Path, previous_size: int) -> bool:
        time.sleep(self.config.stable_check_seconds)
        try:
            now_size = path.stat().st_size
        except OSError:
            return False
        return now_size == previous_size

    def _blank_file_record(self, key: str) -> dict:
        return {
            "key": key,
            "arrivals": {},
            "moves": {},
            "sizes": {},
            "large_file": False,
            "sla_breach_sent": False,
            "last_large_status_at": None,
        }

    def _file_key(self, filename: str) -> str:
        return Path(filename).stem

    def _mark_arrival(self, record: dict, step_name: str, snap: FileSnapshot, now_ist: datetime, now_est: datetime) -> None:
        arrivals = record.setdefault("arrivals", {})
        if step_name in arrivals:
            return

        arrivals[step_name] = now_ist.isoformat()
        record.setdefault("sizes", {})[step_name] = snap.size
        if snap.size >= self.config.large_file_threshold_mb * 1024 * 1024:
            record["large_file"] = True

        subj = f"File Arrival Alert - {step_name}"
        body = (
            "Hi Team,\n"
            f"File Received: {snap.path.name}\n"
            f"Size: {snap.size} bytes\n"
            f"Arrival Time IST: {now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"Arrival Time EST: {now_est.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        )
        alert_key = f"arrival|{step_name}|{record['key']}"
        if self.state.mark_alert(alert_key):
            self.mailer.send_mail(self.config.team1, subj, body)
        self.logger.info("File received | step=%s | file=%s | size=%s", step_name, snap.path.name, snap.size)

    def _mark_moved_if_needed(self, record: dict, from_step: str, to_step: str, now_ist: datetime, now_est: datetime) -> None:
        moves = record.setdefault("moves", {})
        if from_step not in record.get("arrivals", {}):
            return
        if moves.get(from_step):
            return

        moves[from_step] = now_ist.isoformat()
        subj = f"File Moved Alert - {from_step} to {to_step}"
        body = (
            "Hi Team,\n"
            f"File Moved: {record['key']}\n"
            f"Size: {record.get('sizes', {}).get(from_step, 'unknown')} bytes\n"
            f"Moved Time IST: {now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"Moved Time EST: {now_est.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        )
        alert_key = f"moved|{from_step}|{record['key']}"
        if self.state.mark_alert(alert_key):
            self.mailer.send_mail(self.config.team1, subj, body)
        self.logger.info("File moved | from=%s | to=%s | file=%s", from_step, to_step, record["key"])

        if to_step == "Step4":
            self._send_completion(record, now_ist)

    def _send_completion(self, record: dict, now_ist: datetime) -> None:
        s1 = record.get("arrivals", {}).get("Step1")
        s4 = record.get("arrivals", {}).get("Step4")
        if not s1 or not s4:
            return
        elapsed = int((datetime.fromisoformat(s4) - datetime.fromisoformat(s1)).total_seconds() // 60)
        subj = "File Processing Completed"
        body = (
            "Hi Team,\n"
            f"File {record['key']} completed.\n"
            f"Processing Time: {elapsed} minutes\n"
            f"Completed At: {now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        )
        alert_key = f"completed|{record['key']}"
        if self.state.mark_alert(alert_key):
            self.mailer.send_mail(self.config.internal_team, subj, body)

    def _evaluate_stuck_and_sla(self, now_ist: datetime, now_est: datetime) -> None:
        files = self.state.get("files", {})
        for key, record in files.items():
            arrivals = record.get("arrivals", {})
            if "Step4" in arrivals:
                continue

            for idx, step in enumerate(self.config.steps[:-1]):
                curr = step.name
                nxt = self.config.steps[idx + 1].name
                if curr not in arrivals or nxt in arrivals:
                    continue

                arrived_at = datetime.fromisoformat(arrivals[curr])
                age_min = (now_ist - arrived_at).total_seconds() / 60.0

                if record.get("large_file"):
                    self._handle_large_file_status(key, curr, age_min, record, now_ist)
                elif age_min >= self.config.stuck_minutes:
                    self._send_stuck_alert_once(key, curr, record, now_ist, now_est)

    def _send_stuck_alert_once(self, key: str, step_name: str, record: dict, now_ist: datetime, now_est: datetime) -> None:
        alert_key = f"stuck|{step_name}|{key}"
        if not self.state.mark_alert(alert_key):
            return

        body = (
            "Hi Team,\n"
            f"File {key} appears stuck.\n"
            f"Size: {record.get('sizes', {}).get(step_name, 'unknown')} bytes\n"
            f"Time IST: {now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"Time EST: {now_est.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        )
        self.mailer.send_mail(self.config.internal_team, f"Stuck File Alert - {step_name}", body)
        self.logger.warning("Stuck alert | step=%s | file=%s", step_name, key)

    def _handle_large_file_status(self, key: str, step_name: str, age_min: float, record: dict, now_ist: datetime) -> None:
        last_status = record.get("last_large_status_at")
        should_send_status = False
        if last_status is None:
            should_send_status = True
        else:
            last_dt = datetime.fromisoformat(last_status)
            should_send_status = (now_ist - last_dt) >= timedelta(minutes=self.config.large_file_status_minutes)

        if should_send_status:
            subj = f"Large File In Progress - {step_name}"
            body = (
                "Hi Team,\n"
                f"File {key} is still processing.\n"
                f"Elapsed: {int(age_min)} minutes\n"
            )
            status_key = f"large_status|{step_name}|{key}|{now_ist.strftime('%Y%m%d%H%M')}"
            if self.state.mark_alert(status_key):
                self.mailer.send_mail(self.config.internal_team, subj, body)
            record["last_large_status_at"] = now_ist.isoformat()

        if age_min >= self.config.large_file_sla_minutes and not record.get("sla_breach_sent"):
            subj = f"SLA Breach Alert - {step_name}"
            body = (
                "Hi Team,\n"
                f"File {key} breached SLA.\n"
                f"Elapsed: {int(age_min)} minutes\n"
            )
            self.mailer.send_mail(self.config.internal_team, subj, body)
            record["sla_breach_sent"] = True
            self.logger.warning("SLA breach | step=%s | file=%s", step_name, key)

    def _send_not_received_alerts(self, snapshots: dict[str, dict[str, FileSnapshot]]) -> None:
        now_ist = datetime.now(tz=IST)

        for step in self.config.steps:
            in_window = self._in_window(step, now_ist)
            if in_window:
                continue
            if now_ist.time() <= step.end_time:
                continue

            date_token = now_ist.strftime("%Y%m%d")
            valid = self._valid_files_in_step(step, snapshots.get(step.name, {}), date_token)
            if len(valid) >= step.expected_count:
                continue

            once_key = f"not_received|{step.name}|{date_token}"
            if not self.state.mark_alert(once_key):
                continue

            subj = f"File Not Received Alert - {step.name}"
            body = "Hi Team,\nExpected files not received within monitoring window.\n"
            self.mailer.send_mail(self.config.internal_team, subj, body)
            self.logger.warning("Not received alert | step=%s | found=%s expected=%s", step.name, len(valid), step.expected_count)
