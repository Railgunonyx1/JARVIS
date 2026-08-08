"""Email Client — Send and read emails via SMTP/IMAP.

Provides basic email operations for JARVIS.
"""
import logging
import time
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger("external.email_client")


@dataclass
class EmailMessage:
    """Represents an email message."""
    to: str = ""
    subject: str = ""
    body: str = ""
    from_addr: str = ""
    date: str = ""
    uid: str = ""
    is_read: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "to": self.to, "subject": self.subject,
            "body": self.body[:500], "from": self.from_addr,
            "date": self.date, "uid": self.uid,
        }


class EmailClient:
    """Send and read emails via SMTP/IMAP."""

    def __init__(self, smtp_host: str = "", smtp_port: int = 587,
                 imap_host: str = "", imap_port: int = 993,
                 email_addr: str = "", password: str = ""):
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._email = email_addr
        self._password = password
        self._sent_count = 0

    def send_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Send an email."""
        if not self._smtp_host or not self._email:
            return {"success": False, "error": "SMTP not configured"}

        try:
            msg = MIMEMultipart()
            msg["From"] = self._email
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                server.starttls()
                server.login(self._email, self._password)
                server.send_message(msg)

            self._sent_count += 1
            return {"success": True, "to": to, "subject": subject}
        except Exception as e:
            logger.error("Email send failed: %s", e)
            return {"success": False, "error": str(e)}

    def read_emails(self, folder: str = "INBOX", count: int = 10) -> List[EmailMessage]:
        """Read recent emails from the inbox."""
        if not self._imap_host or not self._email:
            return []

        try:
            mail = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
            mail.login(self._email, self._password)
            mail.select(folder)

            _, data = mail.search(None, "ALL")
            mail_ids = data[0].split()

            messages = []
            for mid in mail_ids[-count:]:
                _, msg_data = mail.fetch(mid, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                messages.append(EmailMessage(
                    subject=msg.get("Subject", ""),
                    from_addr=msg.get("From", ""),
                    date=msg.get("Date", ""),
                    uid=mid.decode(),
                    body=self._get_body(msg),
                ))

            mail.logout()
            return messages
        except Exception as e:
            logger.error("Email read failed: %s", e)
            return []

    def _get_body(self, msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    return part.get_payload(decode=True).decode(errors="replace")[:500]
        return msg.get_payload(decode=True).decode(errors="replace")[:500] if msg.get_payload() else ""

    def get_stats(self) -> Dict[str, Any]:
        return {
            "configured": bool(self._smtp_host and self._email),
            "sent_count": self._sent_count,
            "email": self._email[:3] + "***" if self._email else "",
        }


_email_instance: Optional[EmailClient] = None


def get_email_client() -> EmailClient:
    global _email_instance
    if _email_instance is None:
        _email_instance = EmailClient()
    return _email_instance
