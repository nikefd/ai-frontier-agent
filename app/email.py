"""Email sending via SMTP (stdlib only, no dependency).

Used for account email-verification links. When SMTP isn't configured
(host/user/password empty) sending is a no-op that logs a warning, so the app
still runs and registration still works — just without the verification mail.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from .settings import settings

log = logging.getLogger("aif.email")


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


def send_email(to: str, subject: str, html: str, text: str = "") -> bool:
    """Send one email. Returns True on success, False if not configured / failed.

    Never raises — callers (e.g. registration) must not break when mail is down.
    """
    if not smtp_configured():
        log.warning("SMTP not configured — skipping email to %s (%s)", to, subject)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg.set_content(text or "请使用支持 HTML 的邮件客户端查看。")
    msg.add_alternative(html, subtype="html")

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls(context=ctx)
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True
    except Exception as e:  # noqa: broad-except
        log.warning("failed to send email to %s: %s", to, e)
        return False


def send_verification_email(to: str, link: str) -> bool:
    subject = "验证你的邮箱 · AI 前沿 Agent"
    html = f"""\
<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:24px">
  <h2 style="margin:0 0 12px">验证你的邮箱</h2>
  <p style="color:#475569;line-height:1.6">
    你好，感谢注册 <b>AI 前沿 Agent</b>。请点击下面的按钮验证你的邮箱地址：
  </p>
  <p style="margin:24px 0">
    <a href="{link}" style="background:#7c3aed;color:#fff;text-decoration:none;
       padding:10px 20px;border-radius:8px;display:inline-block">验证邮箱</a>
  </p>
  <p style="color:#94a3b8;font-size:13px;line-height:1.6">
    按钮无法点击？复制下面的链接到浏览器打开：<br>
    <span style="word-break:break-all">{link}</span><br><br>
    链接 24 小时内有效。如果不是你本人操作，忽略此邮件即可。
  </p>
</div>"""
    text = f"验证你的邮箱：{link}\n链接 24 小时内有效。"
    return send_email(to, subject, html, text)
