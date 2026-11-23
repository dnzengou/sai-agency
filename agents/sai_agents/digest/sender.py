"""SMTP digest sender with a lossless dry-run fallback.

If SMTP is configured, sends personalised digests; otherwise writes a preview
HTML file and reports each recipient as ``dry_run`` (nothing is silently lost).
The SMTP transport is injectable so tests never open a socket.
"""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Callable, Dict, List, Optional

from sai_agents.logging_setup import get_logger

log = get_logger("digest.sender")


@dataclass
class SMTPConfig:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    starttls: bool = True
    from_addr: str = "Deal Radar <deals@sai-agency.example>"

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "SMTPConfig":
        env = env if env is not None else dict(os.environ)
        return cls(
            host=env.get("SMTP_HOST", ""),
            port=int(env.get("SMTP_PORT", "587")),
            user=env.get("SMTP_USER", ""),
            password=env.get("SMTP_PASSWORD", ""),
            starttls=env.get("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes", "on"},
            from_addr=env.get("DIGEST_FROM", "Deal Radar <deals@sai-agency.example>"),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.host)


class DigestSender:
    def __init__(
        self,
        config: Optional[SMTPConfig] = None,
        smtp_factory: Optional[Callable[[str, int], smtplib.SMTP]] = None,
        preview_path: Optional[str] = None,
    ) -> None:
        self.config = config or SMTPConfig.from_env()
        self._smtp_factory = smtp_factory or (lambda host, port: smtplib.SMTP(host, port, timeout=30))
        self.preview_path = preview_path

    def _build_message(self, to_addr: str, subject: str, html_body: str, text_body: str) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.config.from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        return msg

    def send(
        self,
        subscribers: List[Dict],
        subject: str,
        html_body: str,
        text_body: str,
    ) -> Dict:
        """Send to all subscribers. Returns {sent, dry_run, failed}."""
        result = {"sent": 0, "dry_run": 0, "failed": 0, "recipients": len(subscribers)}

        if not self.config.enabled:
            # Dry-run: write a preview so the digest is never silently dropped.
            if self.preview_path:
                Path(self.preview_path).write_text(html_body, encoding="utf-8")
            log.warning("digest.dry_run", reason="SMTP not configured", recipients=len(subscribers),
                        preview=self.preview_path)
            result["dry_run"] = len(subscribers)
            return result

        smtp = None
        try:
            smtp = self._smtp_factory(self.config.host, self.config.port)
            if self.config.starttls:
                smtp.starttls()
            if self.config.user:
                smtp.login(self.config.user, self.config.password)
            for sub in subscribers:
                msg = self._build_message(sub["email"], subject, html_body, text_body)
                try:
                    smtp.send_message(msg)
                    result["sent"] += 1
                except Exception as exc:  # one bad recipient must not stop the rest
                    log.error("digest.send_failed", email=sub.get("email"), error=str(exc))
                    result["failed"] += 1
        finally:
            if smtp is not None:
                try:
                    smtp.quit()
                except Exception:  # pragma: no cover
                    pass
        log.info("digest.sent", **{k: result[k] for k in ("sent", "failed")})
        return result
