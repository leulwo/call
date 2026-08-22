"""ExamPaper Refine - Email notification service.

Sends async notification emails to contributors when their paper finishes processing.
"""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_paper_ready_email(
    to_email: str,
    paper_id: str,
    title: str | None = None,
    download_url: str | None = None,
) -> bool:
    """Send an email notification that an uploaded paper has been refined and is ready.

    Returns True if sent successfully or False if skipped/failed.
    """
    settings = get_settings()

    if not settings.smtp_host or not to_email:
        logger.debug("SMTP not configured or no email provided; skipping notification.")
        return False

    display_title = title or f"Paper {paper_id}"
    url = download_url or f"http://{settings.host}:{settings.port}/api/papers/{paper_id}/download/refined"

    message = MIMEMultipart("alternative")
    message["Subject"] = f"Your exam paper is ready! [{display_title}]"
    message["From"] = settings.smtp_from
    message["To"] = to_email

    text_body = f"""Hello,

Thank you for contributing to the ExamPaper Refine open-source repository!

Your paper '{display_title}' has finished processing and the refined, typeset PDF is ready.

You can download it here:
{url}

Best regards,
The ExamPaper Refine Team
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; }}
    .header {{ font-size: 20px; font-weight: bold; color: #1e293b; margin-bottom: 16px; }}
    .btn {{ display: inline-block; padding: 12px 24px; background-color: #2563eb; color: #ffffff !important; text-decoration: none; border-radius: 6px; font-weight: 500; margin: 20px 0; }}
    .footer {{ font-size: 12px; color: #64748b; margin-top: 24px; border-top: 1px solid #e2e8f0; padding-top: 12px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">Your Exam Paper is Ready! 🎉</div>
    <p>Thank you for contributing to the <strong>ExamPaper Refine</strong> open-source repository.</p>
    <p>Your paper <strong>{display_title}</strong> has finished processing and the refined PDF has been typeset.</p>
    <a href="{url}" class="btn">Download Refined PDF</a>
    <p>Or open directly in your browser: <br><a href="{url}">{url}</a></p>
    <div class="footer">
      ExamPaper Refine — Turning messy exam papers into clean, typeset documents.
    </div>
  </div>
</body>
</html>
"""

    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user if settings.smtp_user else None,
            password=settings.smtp_pass if settings.smtp_pass else None,
            start_tls=settings.smtp_tls,
            timeout=15,
        )
        logger.info(f"Sent completion email to {to_email} for paper {paper_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to send email notification to {to_email}: {e}")
        return False
