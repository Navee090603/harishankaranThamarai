from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
EST = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class StepConfig:
    name: str
    folder: Path
    extension: str
    expected_count: int
    start_time: time
    end_time: time


@dataclass
class AppConfig:
    steps: list[StepConfig] = field(default_factory=list)
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_timeout_seconds: int = 20
    from_mail: str = "Naveen.Thiyagasundaram@caresource.com"
    internal_team: list[str] = field(default_factory=lambda: ["Hari.shankaran@caresource.com"])
    team1: list[str] = field(default_factory=lambda: ["Thamaraipriya.Madhaiyan@caresource.com"])
    poll_interval_seconds: int = 5
    stable_check_seconds: int = 5
    stuck_minutes: int = 5
    large_file_threshold_mb: int = 700
    large_file_sla_minutes: int = 150
    large_file_status_minutes: int = 30
    mail_retries: int = 3
    mail_retry_delay_seconds: int = 10
    state_file: Path = Path("runtime/state.json")
    lock_file: Path = Path("runtime/monitor.lock")
    log_dir: Path = Path("logs")
    log_backup_days: int = 14



def _hm(v: str) -> time:
    hh, mm = v.split(":", maxsplit=1)
    return time(hour=int(hh), minute=int(mm))


def load_config() -> AppConfig:
    # Configurable time windows (IST)
    step1_start = _hm("06:00")
    step1_end = _hm("08:30")

    step2_start = _hm("06:00")
    step2_end = _hm("08:30")

    step3_start = _hm("06:00")
    step3_end = _hm("08:30")

    step4_start = _hm("06:00")
    step4_end = _hm("08:30")

    return AppConfig(
        steps=[
            StepConfig(
                name="Step1",
                folder=Path(r"C:\Users\karun\Downloads\ALT\01_VU\Altruista"),
                extension=".txt",
                expected_count=2,
                start_time=step1_start,
                end_time=step1_end,
            ),
            StepConfig(
                name="Step2",
                folder=Path(r"C:\Users\karun\Downloads\ALT\Step2"),
                extension=".txt",
                expected_count=2,
                start_time=step2_start,
                end_time=step2_end,
            ),
            StepConfig(
                name="Step3",
                folder=Path(r"C:\Users\karun\Downloads\ALT\Step_3"),
                extension=".edi",
                expected_count=2,
                start_time=step3_start,
                end_time=step3_end,
            ),
            StepConfig(
                name="Step4",
                folder=Path(r"C:\Users\karun\Downloads\ALT\Step4"),
                extension=".edi",
                expected_count=2,
                start_time=step4_start,
                end_time=step4_end,
            ),
        ]
    )
