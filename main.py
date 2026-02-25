from __future__ import annotations

import signal
import sys
from datetime import datetime

from config import EST, IST, load_config
from logger_module import setup_logger
from mailer import Mailer
from monitor import FileMonitor
from singleton_lock import SingleInstanceLock
from state_store import StateStore


def main() -> int:
    config = load_config()
    logger = setup_logger(config.log_dir, config.log_backup_days)

    now_ist = datetime.now(tz=IST)
    now_est = now_ist.astimezone(EST)
    logger.info("System startup | IST=%s | EST=%s", now_ist.isoformat(), now_est.isoformat())

    lock = SingleInstanceLock(config.lock_file)
    if not lock.acquire():
        logger.error("Another instance is already running, exiting")
        return 2

    state = StateStore(config.state_file)
    state.load()

    mailer = Mailer(
        host=config.smtp_host,
        port=config.smtp_port,
        timeout_seconds=config.smtp_timeout_seconds,
        from_mail=config.from_mail,
        retries=config.mail_retries,
        retry_delay_seconds=config.mail_retry_delay_seconds,
        logger=logger,
    )

    monitor = FileMonitor(config=config, state=state, mailer=mailer, logger=logger)

    def _shutdown_handler(signum, frame):
        logger.info("Signal %s received, shutting down", signum)
        monitor.shutdown()

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    try:
        monitor.run()
        return 0
    finally:
        state.save()
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
