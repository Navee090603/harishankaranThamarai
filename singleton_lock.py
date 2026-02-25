from __future__ import annotations

from pathlib import Path


class SingleInstanceLock:
    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self.fp = None

    def acquire(self) -> bool:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.fp = self.lock_file.open("a+")
        try:
            import fcntl

            fcntl.flock(self.fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except ImportError:
            try:
                import msvcrt

                msvcrt.locking(self.fp.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
        except OSError:
            return False

    def release(self) -> None:
        if self.fp is None:
            return
        try:
            import fcntl

            fcntl.flock(self.fp.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        self.fp.close()
        self.fp = None
