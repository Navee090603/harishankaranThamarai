# File Monitoring Automation (Step1 -> Step4)

Production-focused Python monitor for end-to-end file flow, SLA checks, and SMTP alerts (port 25).

## Run

```bash
python3 main.py
```

## Modules

- `config.py`: All configurable settings (windows, folders, SLA, mail, timers).
- `monitor.py`: Workflow engine, validation, stuck/SLA logic, restart recovery.
- `mailer.py`: SMTP sender with retries and timeout handling.
- `state_store.py`: Idempotent persisted state (`runtime/state.json`) for restart safety.
- `logger_module.py`: Console + rotating file logs in IST format.
- `singleton_lock.py`: Prevents double instance.

## Notes

- Time windows are configured in IST and converted to EST for mail content.
- File checks reject wrong extension, missing date token, zero-byte, temporary, and growing files.
- Stuck alert: 5 minutes for normal files.
- Large files (`>= 700MB`) use 30-minute status mail and SLA breach logic.
- Daily reset is automatic on IST date change.
