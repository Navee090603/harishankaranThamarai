from __future__ import annotations

import smtplib
import socket
from email.message import EmailMessage
from time import sleep
import logging


class Mailer:
    def __init__(
        self,
        host: str,
        port: int,
        timeout_seconds: int,
        from_mail: str,
        retries: int,
        retry_delay_seconds: int,
        logger: logging.Logger,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.from_mail = from_mail
        self.retries = retries
        self.retry_delay_seconds = retry_delay_seconds
        self.logger = logger

    def send_mail(self, to_list: list[str], subject: str, body: str) -> bool:
        msg = EmailMessage()
        msg["From"] = self.from_mail
        msg["To"] = ", ".join(to_list)
        msg["Subject"] = subject
        msg.set_content(body)

        for attempt in range(1, self.retries + 1):
            try:
                with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as server:
                    server.send_message(msg)
                self.logger.info("Mail sent | to=%s | subject=%s", to_list, subject)
                return True
            except (smtplib.SMTPException, OSError, socket.timeout) as exc:
                self.logger.error(
                    "Mail failed attempt %s/%s | to=%s | subject=%s | error=%s",
                    attempt,
                    self.retries,
                    to_list,
                    subject,
                    exc,
                )
                if attempt < self.retries:
                    sleep(self.retry_delay_seconds)
        return False
