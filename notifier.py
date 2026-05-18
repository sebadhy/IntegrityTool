"""
notifier.py — Envío de alertas por email cuando se detectan señales de alta atención.

Usa SMTP con TLS (compatible con Gmail con contraseña de aplicación).
Configuración via variables de entorno SMTP_* en .env
"""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()
LOGGER = logging.getLogger(__name__)


def send_alert_email(
    document_name: str,
    brief: dict,
    top_findings: list[dict],
    recipients: list[str],
) -> tuple[bool, str]:
    """
    Envía alerta de red flag por email a los destinatarios indicados.
    Retorna (success: bool, message: str).
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_user or not smtp_password:
        return False, "SMTP no configurado. Define SMTP_USER y SMTP_PASSWORD en .env"

    if not recipients:
        return False, "No hay destinatarios activos en la base de datos."

    subject = f"[Alerta neutralidad] {document_name}"
    body = _build_html_body(document_name, brief, top_findings)

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(body, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, recipients, msg.as_string())

        LOGGER.info("Alerta enviada a %d destinatario(s).", len(recipients))
        return True, f"Alerta enviada a {len(recipients)} destinatario(s): {', '.join(recipients)}"

    except smtplib.SMTPAuthenticationError:
        return False, (
            "Error de autenticación SMTP. "
            "Para Gmail use una Contraseña de Aplicación (no la contraseña normal). "
            "Actívela en: Cuenta Google → Seguridad → Verificación en 2 pasos → Contraseñas de app."
        )
    except smtplib.SMTPException as exc:
        LOGGER.error("Error SMTP: %s", exc)
        return False, f"Error SMTP: {exc}"
    except TimeoutError:
        return False, "Tiempo de espera agotado al conectar con el servidor SMTP."
    except Exception as exc:
        LOGGER.error("Error enviando email: %s", exc)
        return False, f"Error inesperado: {exc}"


# ---------------------------------------------------------------------------
# Construcción del cuerpo HTML
# ---------------------------------------------------------------------------

def _build_html_body(document_name: str, brief: dict, top_findings: list[dict]) -> str:
    attention = brief.get("overall_attention_level", "No disponible")
    summary = brief.get("document_summary", "No disponible")
    topics = brief.get("main_review_topics", [])
    questions = brief.get("suggested_human_review_questions", [])
    note = brief.get("methodological_note", "")

    badge_color = {"Alto": "#dc2626", "Medio": "#d97706", "Bajo": "#16a34a"}.get(attention, "#6b7280")
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    topics_html = "".join(f"<li>{_esc(t)}</li>" for t in topics[:5]) if topics else "<li>No disponible</li>"
    questions_html = "".join(f"<li>{_esc(q)}</li>" for q in questions[:4])

    findings_html = ""
    for f in top_findings[:3]:
        patron = _esc(f.get("patrón detectado") or f.get("pattern_name") or "Hallazgo")
        pagina = f.get("página") or f.get("page_number") or "?"
        razon = _esc(str(f.get("por qué se sugiere revisar") or f.get("observación prudente") or f.get("rationale") or "")[:220])
        findings_html += f"""
        <div style="border-left:3px solid {badge_color}; padding:8px 14px; margin:8px 0; background:#fafafa; border-radius:0 4px 4px 0;">
            <strong>{patron}</strong> — página {pagina}<br>
            <span style="font-size:13px; color:#555;">{razon}</span>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif; max-width:680px; margin:0 auto; color:#333; background:#f5f5f5; padding:16px;">

<div style="background:#1e3a5f; color:white; padding:16px 24px; border-radius:6px 6px 0 0;">
    <h2 style="margin:0; font-size:17px; font-weight:600;">Sistema de revisión de neutralidad competitiva</h2>
    <p style="margin:4px 0 0; opacity:.75; font-size:13px;">Señal preliminar para revisión humana — Ecuador</p>
</div>

<div style="background:#fff; border:1px solid #ddd; border-top:none; padding:24px; border-radius:0 0 6px 6px;">

    <div style="background:#f8fafc; border-radius:4px; padding:14px; margin-bottom:20px; border:1px solid #e2e8f0;">
        <p style="margin:0 0 2px; font-size:12px; color:#888; text-transform:uppercase; letter-spacing:.5px;">Documento analizado</p>
        <p style="margin:0; font-size:16px; font-weight:bold; color:#1e293b;">{_esc(document_name)}</p>
        <p style="margin:4px 0 0; font-size:12px; color:#94a3b8;">{now}</p>
    </div>

    <div style="margin-bottom:20px;">
        <span style="display:inline-block; background:{badge_color}; color:white; padding:5px 18px; border-radius:20px; font-weight:bold; font-size:14px;">
            Nivel de atención: {_esc(attention)}
        </span>
    </div>

    <h3 style="font-size:14px; color:#1e293b; border-bottom:1px solid #e2e8f0; padding-bottom:6px; margin-top:20px;">Resumen del documento</h3>
    <p style="font-size:14px; line-height:1.7; color:#475569;">{_esc(summary)}</p>

    <h3 style="font-size:14px; color:#1e293b; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">Principales temas para revisión</h3>
    <ul style="font-size:14px; line-height:1.9; color:#475569; padding-left:20px;">{topics_html}</ul>

    {"<h3 style='font-size:14px; color:#1e293b; border-bottom:1px solid #e2e8f0; padding-bottom:6px;'>Hallazgos de alta prioridad</h3>" + findings_html if findings_html else ""}

    {"<h3 style='font-size:14px; color:#1e293b; border-bottom:1px solid #e2e8f0; padding-bottom:6px;'>Preguntas sugeridas para el revisor</h3><ul style='font-size:14px; line-height:1.9; color:#475569; padding-left:20px;'>" + questions_html + "</ul>" if questions_html else ""}

    <div style="background:#fffbeb; border:1px solid #fcd34d; border-radius:4px; padding:12px 16px; margin-top:24px; font-size:12px; color:#78350f;">
        <strong>Nota metodológica:</strong> {_esc(note) or "Las señales identificadas son insumos preliminares para revisión humana. No constituyen dictamen técnico, legal ni determinación de responsabilidad."}
    </div>

</div>
</body></html>"""


def _esc(value: object) -> str:
    from html import escape
    return escape(str(value or ""))
