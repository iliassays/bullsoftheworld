"""Transactional email — provider-agnostic.

Sends via Resend (preferred, branded domain) when RESEND_API_KEY is set, else falls back to SMTP
(the Gmail stopgap) when SMTP_* is set, else logs and no-ops (dev). All sends are best-effort: a mail
failure never breaks the request that triggered it.

`render_email` wraps content in the active tenant's inline-styled, email-client-safe shell.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from bulls.core.config import Settings, get_settings
from bulls.core.tenancy import Tenant

log = logging.getLogger(__name__)

def render_email(
    *,
    tenant: Tenant,
    lang: str,
    heading: str,
    paragraphs: list[str],
    cta_label: str | None,
    cta_url: str | None,
    footer: str,
) -> tuple[str, str]:
    """Return (html, plain_text) for a branded email. Content is pre-localized by the caller."""
    support = tenant.support_email
    brand = html_lib.escape(tenant.display_name)
    tagline = html_lib.escape(tenant.tagline_bn if lang == "bn" else tenant.tagline_en)
    accent = html_lib.escape(tenant.theme.accent, quote=True)
    logo_url = html_lib.escape(tenant.logo_url, quote=True)
    contact_html = (
        f'<a href="mailto:{html_lib.escape(support, quote=True)}" style="color:#777;">'
        f"{html_lib.escape(support)}</a>"
        if support
        else ""
    )
    body_html = "".join(
        '<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#1a1a1a;">'
        f"{html_lib.escape(p)}</p>"
        for p in paragraphs
    )
    cta_html = ""
    if cta_label and cta_url:
        # Just the button — no raw link below it (the long token URL confuses users).
        cta_html = (
            f'<p style="margin:24px 0;"><a href="{html_lib.escape(cta_url, quote=True)}" '
            f'style="background:{accent};color:#151a21;font-weight:700;text-decoration:none;'
            'padding:13px 26px;border-radius:9999px;display:inline-block;font-size:15px;">'
            f"{html_lib.escape(cta_label)}</a></p>"
        )
    heading_html = html_lib.escape(heading)
    footer_html = html_lib.escape(footer)
    html = f"""\
<!doctype html><html><body style="margin:0;background:#f3f4f6;padding:24px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;border:1px solid #e5e7eb;">
    <div style="background:#151a21;padding:16px 24px;">
      <img src="{logo_url}" width="28" height="28" alt="" style="vertical-align:middle;border:0;"/>
      <span style="color:#fff;font-weight:700;font-size:16px;margin-left:8px;vertical-align:middle;">{brand}</span>
      <span style="color:{accent};font-size:11px;margin-left:8px;vertical-align:middle;">{tagline}</span>
    </div>
    <div style="padding:24px;">
      <h1 style="margin:0 0 16px;font-size:19px;color:#151a21;">{heading_html}</h1>
      {body_html}
      {cta_html}
      <p style="margin:20px 0 0;font-size:11px;color:#999;border-top:1px solid #eee;padding-top:14px;">{footer_html}</p>
      <p style="margin:8px 0 0;font-size:11px;color:#999;">{brand} · {contact_html}</p>
    </div>
  </div>
</body></html>"""
    text_lines = [heading, "", *paragraphs]
    if cta_label and cta_url:
        text_lines.extend(["", f"{cta_label}: {cta_url}"])
    text_lines.extend(["", footer])
    if support:
        text_lines.extend(["", f"{tenant.display_name} · {support}"])
    return html, "\n".join(text_lines)


async def send_email(
    to: str, subject: str, html: str, text: str, *, tenant: Tenant
) -> bool:
    s = get_settings()
    if s.resend_api_key:
        return await _send_resend(s, tenant, to, subject, html, text)
    if s.smtp_server and s.smtp_username:
        return await asyncio.to_thread(_send_smtp, s, tenant, to, subject, html, text)
    log.warning("email not configured — skipping send to %s (subject: %s)", to, subject)
    return False


async def _send_resend(
    s: Settings, tenant: Tenant, to: str, subject: str, html: str, text: str
) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {s.resend_api_key}"},
                json={
                    "from": tenant.email_from,
                    "to": [to],
                    "reply_to": tenant.support_email,
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
            )
        if r.status_code >= 300:
            log.error("resend send failed %s: %s", r.status_code, r.text)
            return False
        return True
    except Exception:
        log.exception("resend send error")
        return False


def _send_smtp(
    s: Settings, tenant: Tenant, to: str, subject: str, html: str, text: str
) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = tenant.email_from
    msg["To"] = to
    msg["Reply-To"] = tenant.support_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP(s.smtp_server, s.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(s.smtp_username, s.smtp_password)
            server.send_message(msg)
        return True
    except Exception:
        log.exception("smtp send failed")
        return False
