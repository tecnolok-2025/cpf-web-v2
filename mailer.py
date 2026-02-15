
import os
import smtplib
from email.message import EmailMessage
from typing import Optional


def _mailer_log(msg: str) -> None:
    """Log del mailer para debug (sale en Render Runtime Logs)."""
    try:
        print(f"[MAILER] {msg}", flush=True)
    except Exception:
        # Nunca romper la app por un problema de logging
        pass

def _bool_env(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or default).strip().lower() in ("1","true","yes","y","on")

def is_configured() -> bool:
    # Acepta ambas variantes: CPF_SMTP_* (preferida) y SMTP_* (por compatibilidad)
    host = (os.getenv("CPF_SMTP_HOST") or os.getenv("SMTP_HOST") or "").strip()
    user = (os.getenv("CPF_SMTP_USER") or os.getenv("SMTP_USER") or "").strip()
    pwd  = (os.getenv("CPF_SMTP_PASS") or os.getenv("SMTP_PASS") or "").strip()
    frm  = (os.getenv("CPF_SMTP_FROM") or os.getenv("SMTP_FROM") or "").strip()
    return bool(host and user and pwd and frm)

def app_url() -> str:
    """URL público del sistema para incluir en los mails.

    Sugerido: configurar CPF_APP_URL con el dominio final (ej.: https://cpf-guion-web-render.com)
    """
    return (os.getenv("CPF_APP_URL") or "https://cpf-web.onrender.com").strip().rstrip("/")

def _send(to_email: str, subject: str, body: str) -> bool:
    if not to_email:
        _mailer_log("SKIP: destinatario vacío")
        return False
    if not is_configured():
        _mailer_log("NO CONFIG: faltan variables SMTP_* (HOST/USER/PASS/FROM)")
        return False

    host = (os.getenv("CPF_SMTP_HOST") or os.getenv("SMTP_HOST") or "").strip()
    port = int((os.getenv("CPF_SMTP_PORT") or os.getenv("SMTP_PORT") or "587").strip())
    user = (os.getenv("CPF_SMTP_USER") or os.getenv("SMTP_USER") or "").strip()
    pwd  = (os.getenv("CPF_SMTP_PASS") or os.getenv("SMTP_PASS") or "").strip()
    frm  = (os.getenv("CPF_SMTP_FROM") or os.getenv("SMTP_FROM") or "").strip()
    use_tls = _bool_env("CPF_SMTP_TLS", os.getenv("SMTP_TLS") or "1")

    msg = EmailMessage()
    msg["From"] = frm
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    # Log de intención (sin exponer contraseña)
    _mailer_log(f"SEND: to={to_email!r} subj={subject!r} via={host}:{port} user={user!r} tls={use_tls}")

    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            if use_tls:
                s.starttls()
            s.login(user, pwd)
            refused = s.send_message(msg)  # dict de destinatarios rechazados

        if refused:
            _mailer_log(f"REFUSED: {refused!r}")
            return False

        _mailer_log("OK")
        return True
    except Exception as e:
        # Nunca romper la app si falla el mail
        _mailer_log(f"FAIL: to={to_email!r} subject={subject!r} err={e!r}")
        return False

def notify_interest_owner(owner_email: str, owner_name: str, kind: str, title: str, company: str = "") -> bool:
    url = app_url()
    subject = "CPF: Nuevo interesado en tu publicación"
    body = f"""Hola {owner_name or ''},

Hay un nuevo interesado en una publicación tuya dentro de CPF (Sistema de Requerimientos sin precios).

Publicación:
- Tipo: {kind}
- Título: {title}
- Empresa: {company or '(Sin empresa)'}

Para revisar y aceptar/rechazar la solicitud, ingresá al sistema:
{url}

>>> Ingreso directo: {url}

Importante: por privacidad, los datos del interesado se muestran recién cuando aceptás la solicitud.

Saludos,
CPF – Sistema de Requerimientos (sin precios)

*** IMPORTANTE: Por favor NO respondas este correo. Es una notificación automática. ***
"""
    return _send(owner_email, subject, body)

def notify_interest_sender(sender_email: str, sender_name: str, kind: str, title: str, company: str = "") -> bool:
    url = app_url()
    subject = "CPF: Solicitud de contacto enviada"
    body = f"""Hola {sender_name or ''},

Tu solicitud de contacto fue registrada correctamente en CPF.

Publicación seleccionada:
- Tipo: {kind}
- Título: {title}
- Empresa: {company or '(Sin empresa)'}

Estado actual: PENDIENTE (el dueño debe aceptar o rechazar).
Podés seguir el estado ingresando al sistema:
{url}

>>> Ingreso directo: {url}

Saludos,
CPF – Sistema de Requerimientos (sin precios)

*** IMPORTANTE: Por favor NO respondas este correo. Es una notificación automática. ***
"""
    return _send(sender_email, subject, body)

def notify_accept_both(owner_email: str, owner_name: str, sender_email: str, sender_name: str, kind: str, title: str, company: str = "") -> None:
    url = app_url()

    # Mail al interesado
    subject_i = "CPF: Tu solicitud fue aceptada"
    body_i = f"""Hola {sender_name or ''},

¡Buenas noticias! El dueño de la publicación aceptó tu solicitud de contacto.

Publicación:
- Tipo: {kind}
- Título: {title}
- Empresa: {company or '(Sin empresa)'}

Ingresá al sistema para ver los datos de contacto habilitados:
{url}

>>> Ingreso directo: {url}

Saludos,
CPF – Sistema de Requerimientos (sin precios)

*** IMPORTANTE: Por favor NO respondas este correo. Es una notificación automática. ***
"""
    _send(sender_email, subject_i, body_i)

    # Mail al dueño (confirmación)
    subject_o = "CPF: Aceptaste una solicitud de contacto"
    body_o = f"""Hola {owner_name or ''},

Confirmación: aceptaste una solicitud de contacto vinculada a tu publicación.

Publicación:
- Tipo: {kind}
- Título: {title}
- Empresa: {company or '(Sin empresa)'}

Ingresá al sistema para ver el vínculo en tu panel de Interesados:
{url}

>>> Ingreso directo: {url}

Saludos,
CPF – Sistema de Requerimientos (sin precios)

*** IMPORTANTE: Por favor NO respondas este correo. Es una notificación automática. ***
"""
    _send(owner_email, subject_o, body_o)


def send_password_reset_code(to_email: str, person_name: str, code: str, expires_minutes: int = 20) -> bool:
    url = app_url()
    subject = "CPF: Clave provisoria para restablecer tu contraseña"
    body = f"""Hola {person_name or ''},

Recibimos un pedido de restablecimiento de contraseña en CPF (Sistema de Requerimientos sin precios).

Tu CLAVE PROVISORIA es:
{code}

Vigencia: {expires_minutes} minutos.

Cómo usarla:
1) Ingresá a CPF: {url}
2) En el panel de inicio, hacé clic en “Olvidé mi contraseña”.
3) Completá tus datos (Nombre/Empresa/Teléfono/Cámara) y pegá esta clave.
4) Definí tu nueva contraseña.

Si vos NO solicitaste este cambio, podés ignorar este correo. Nadie puede cambiar tu contraseña sin acceso a tu email.

Saludos,
CPF – Sistema de Requerimientos (sin precios)

*** IMPORTANTE: Por favor NO respondas este correo. Es una notificación automática. ***
"""
    return _send(to_email, subject, body)


# --- Backward-compatible alias (used by app.py) ---
def mailer_is_configured() -> bool:
    return is_configured()
