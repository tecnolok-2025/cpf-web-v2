import bcrypt
import os
import sqlite3

from db import (
    conn,
    now_iso,
    log,
    get_super_admin_email,  # legacy (first super admin)
    set_super_admin_email,  # legacy (overwrites list)
    get_super_admin_emails,
    add_super_admin_email,
    remove_super_admin_email,
)

import re



from mailer import is_configured as _mail_is_configured, send_password_reset_code as _send_password_reset_code

def password_is_valid(pw: str) -> tuple[bool, str]:
    """Validación simple de contraseña.

    - Mínimo 8 caracteres
    - Al menos 1 letra
    - Al menos 1 número

    Devuelve (ok, mensaje_para_usuario).
    """
    pw = (pw or "")
    if len(pw) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres."
    if not re.search(r"[A-Za-z]", pw):
        return False, "La contraseña debe incluir al menos una letra."
    if not re.search(r"[0-9]", pw):
        return False, "La contraseña debe incluir al menos un número."
    return True, ""



def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def get_user_by_email(email: str):
    c = conn()
    row = c.execute(
        "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
    ).fetchone()
    c.close()
    # Normalizamos a dict para evitar problemas con sqlite3.Row (no tiene .get)
    return dict(row) if row is not None else None


def create_user(
    email,
    password,
    name=None,
    full_name=None,
    company=None,
    phone=None,
    chamber_id=None,
    role="user",
    approved: bool = True,
):
    """Crea un usuario.

    Compatibilidad:
    - Acepta `name` y/o `full_name` (ambos quedan guardados igual en el esquema nuevo).
    """
    email_n = (email or "").strip().lower()

    # Normalización de nombre
    if full_name and not name:
        name = full_name
    if name and not full_name:
        full_name = name

    # Regla de negocio: el **registro público** debe elegir Cámara/Institución.
    # Aplicamos el bloqueo cuando la cuenta se crea como no-aprobada (flujo de registro)
    # para roles de acceso estándar (empresas/usuarios y asistentes).
    if role in {"user", "assistant"} and (not approved) and chamber_id is None:
        raise ValueError("Seleccioná una Cámara o institución para poder registrarte.")

    c = conn()

    # v43: compatibilidad con esquema viejo (sin full_name) y esquema nuevo (con full_name)
    try:
        c.execute(
            """INSERT INTO users(email, password_hash, name, full_name, company, phone, chamber_id, role, is_approved, created_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                email_n,
                hash_password(password),
                (name or "").strip(),
                (full_name or "").strip(),
                (company or "").strip(),
                (phone or "").strip(),
                chamber_id,
                role,
                1 if approved else 0,
                now_iso(),
            ),
        )
    except Exception:
        c.execute(
            """INSERT INTO users(email, password_hash, name, company, phone, chamber_id, role, is_approved, created_at)
                 VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                email_n,
                hash_password(password),
                (name or "").strip(),
                (company or "").strip(),
                (phone or "").strip(),
                chamber_id,
                role,
                1 if approved else 0,
                now_iso(),
            ),
        )

    c.commit()
    user_id = c.execute("SELECT id FROM users WHERE email = ?", (email_n,)).fetchone()["id"]
    c.close()

    # Si es el primer admin creado, lo registramos como Super Admin (multi)
    if role == "admin" and not get_super_admin_emails():
        add_super_admin_email(email_n)

    log(user_id, "user_created", f"role={role}")
    return user_id
def authenticate(email, password):
    """Devuelve:
    - dict(user) si login OK
    - {'_pending': True, 'email': ...} si la cuenta existe pero está pendiente de aprobación
    - None si credenciales inválidas / inactivo
    """
    u = get_user_by_email(email)
    if not u or not u["is_active"]:
        return None
    # suspensión: existe pero no permite ingresar
    try:
        if int(u.get("is_suspended", 0)) == 1:
            return {"_suspended": True, "email": (email or "").strip().lower()}
    except Exception:
        pass
    if not verify_password(password, u["password_hash"]):
        return None
    # flujo de aprobación
    try:
        if int(u.get("is_approved", 1)) != 1:
            return {"_pending": True, "email": (email or "").strip().lower()}
    except Exception:
        pass
    return dict(u)


def any_admin_exists():
    c = conn()
    row = c.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone()
    c.close()
    return row is not None


def is_super_admin(email: str) -> bool:
    """True si el email corresponde a algún Super Admin configurado."""
    try:
        e = (email or "").strip().lower()
        return e in set(get_super_admin_emails())
    except Exception:
        return False


# ----------------------------
# Password reset (self-service)
# ----------------------------

import secrets
from datetime import datetime, timedelta


def _parse_iso_z(s: str) -> datetime:
    # Stored as 2026-02-13T12:34:56Z
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def _digits_only(s: str) -> str:
    return ''.join(ch for ch in (s or '') if ch.isdigit())


def _norm(s: str) -> str:
    return (s or '').strip().lower()


def _mask_email(email: str) -> str:
    try:
        local, domain = email.split('@', 1)
    except ValueError:
        return email
    if len(local) <= 2:
        local_masked = local[0] + '*'
    else:
        local_masked = local[0] + '*' * (len(local) - 2) + local[-1]
    return f"{local_masked}@{domain}"



# ---------------------------------------------------------------------------
# Password reset: identity matching helpers (tolerant, but still multi-factor)
# ---------------------------------------------------------------------------

def _row_to_dict(r):
    """Convert sqlite3.Row (or dict-like) to a plain dict."""
    if r is None:
        return None
    if isinstance(r, dict):
        return r
    # sqlite3.Row supports .keys() + item access by key
    keys = getattr(r, "keys", None)
    if callable(keys):
        try:
            return {k: r[k] for k in r.keys()}
        except Exception:
            pass
    return None


def _strip_accents(s: str) -> str:
    import unicodedata
    if not s:
        return ""
    return "".join(
        ch for ch in unicodedata.normalize("NFD", str(s)) if unicodedata.category(ch) != "Mn"
    )


def _norm_text(s: str) -> str:
    """Normalize text for fuzzy comparisons: lowercase, no accents, alnum+spaces."""
    import re as _re
    s = _strip_accents(s).lower()
    s = _re.sub(r"[^a-z0-9]+", " ", s)
    s = _re.sub(r"\s+", " ", s).strip()
    return s


def _similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _norm_name(s: str) -> str:
    return _norm_text(s)


def _norm_company(s: str) -> str:
    return _norm_text(s)


def _phone_matches(phone_in: str, phone_db: str, min_digits: int) -> bool:
    """Match phone by last N digits (robust to country code / formatting)."""
    if not phone_in:
        return True
    if not phone_db:
        return False

    phone_in = _digits_only(phone_in)
    phone_db = _digits_only(phone_db)
    if not phone_in or not phone_db:
        return False

    # Require last N digits to match (N configurable)
    if len(phone_in) >= min_digits and len(phone_db) >= min_digits:
        return phone_in[-min_digits:] == phone_db[-min_digits:]

    # Fallback to exact when too short
    return phone_in == phone_db


def find_user_by_identity(full_name: str, company: str, phone: str, chamber_id: int | None = None):
    """
    Finds a user for password reset based on identity fields.
    Uses fuzzy matching on name/company (configurable thresholds) + phone and/or chamber as factors.

    Env vars:
      - CPF_PWRESET_NAME_RATIO (default 0.90)
      - CPF_PWRESET_COMPANY_RATIO (default 0.85)
      - CPF_PWRESET_PHONE_MIN_DIGITS (default 6)
      - CPF_DEBUG_PWRESET (set to 1 for minimal server logs)
    """
    name_in = _norm_name(full_name)
    comp_in = _norm_company(company)
    phone_in = _digits_only(phone or "")

    chamber_in = None
    try:
        if chamber_id not in (None, ""):
            chamber_in = int(chamber_id)
    except Exception:
        chamber_in = None

    name_min = float(os.getenv("CPF_PWRESET_NAME_RATIO", "0.90") or "0.90")
    comp_min = float(os.getenv("CPF_PWRESET_COMPANY_RATIO", "0.85") or "0.85")
    phone_min_digits = int(os.getenv("CPF_PWRESET_PHONE_MIN_DIGITS", "6") or "6")
    debug = (os.getenv("CPF_DEBUG_PWRESET", "0") == "1")

    # If caller provides neither phone nor chamber, tighten thresholds (avoid trivial resets)
    if not phone_in and chamber_in is None:
        name_min = max(name_min, 0.98)
        comp_min = max(comp_min, 0.98)

    c = conn()
    cur = c.cursor()
    rows = cur.execute(
        """
        SELECT id, email, name, company, phone, chamber_id, is_active, is_suspended FROM users
        """
    ).fetchall()
    c.close()

    best = None
    best_score = -1.0

    for r in rows:
        d = _row_to_dict(r)
        if not d:
            continue
        # Optional factor: cámara (sin bloquear cuando hay teléfono)
        chamber_bonus = 0.0
        if chamber_in is not None:
            try:
                db_ch = int(d.get("chamber_id") or 0)
            except Exception:
                db_ch = 0

            # Si NO hay teléfono, la cámara pasa a ser un factor fuerte (evita matches triviales)
            if not phone_in and db_ch and db_ch != chamber_in:
                continue

            # Con teléfono: la cámara solo suma/penaliza levemente
            if db_ch and db_ch == chamber_in:
                chamber_bonus = 0.05
            elif db_ch and db_ch != chamber_in:
                chamber_bonus = -0.05

        # Optional factor: phone must match if provided by UI
        if phone_in:
            if not _phone_matches(phone_in, str(d.get("phone") or ""), phone_min_digits):
                continue

        name_db = _norm_name(d.get("full_name") or d.get("name") or "")
        comp_db = _norm_company(d.get("company") or "")

        name_ratio = _similarity(name_in, name_db) if name_in and name_db else 0.0
        comp_ratio = _similarity(comp_in, comp_db) if comp_in and comp_db else 0.0

        # If user entered something, enforce minimum similarity
        if name_in and name_db and name_ratio < name_min:
            continue
        if comp_in and comp_db and comp_ratio < comp_min:
            continue

        # Score: prioritize name, then company
        score = (name_ratio * 0.65) + (comp_ratio * 0.35) + chamber_bonus

        if score > best_score:
            best_score = score
            best = d

    if debug:
        print(f"[PWRESET] identity_match={'yes' if best else 'no'} best_score={best_score:.3f}")

    return best


def create_password_reset_code(user_id: int, ttl_minutes: int = 20, min_interval_seconds: int = 90):
    """Create/replace a reset code for a user. Returns dict."""
    c = conn()
    row = c.execute(
        "SELECT created_at, expires_at, used_at FROM password_reset_tokens WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()

    now = datetime.utcnow()
    if row and row['created_at']:
        try:
            created = _parse_iso_z(row['created_at']).replace(tzinfo=None)
        except Exception:
            created = None
        if created and (now - created).total_seconds() < float(min_interval_seconds):
            return {"ok": False, "reason": "rate_limited"}

    code = secrets.token_hex(4).upper()  # 8 hex chars
    token_hash = bcrypt.hashpw(code.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    created_at = now_iso()
    expires_at = (datetime.utcnow() + timedelta(minutes=int(ttl_minutes))).replace(microsecond=0).isoformat() + 'Z'

    c.execute(
        """INSERT OR REPLACE INTO password_reset_tokens
              (user_id, token_hash, created_at, expires_at, used_at)
              VALUES (?, ?, ?, ?, NULL)""",
        (int(user_id), token_hash, created_at, expires_at),
    )
    c.commit()

    return {"ok": True, "code": code, "expires_at": expires_at, "ttl_minutes": int(ttl_minutes)}


def verify_password_reset_code(user_id: int, code: str):
    c = conn()
    row = c.execute(
        "SELECT token_hash, expires_at, used_at FROM password_reset_tokens WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()

    if not row:
        return {"ok": False, "reason": "not_found"}
    if row['used_at']:
        return {"ok": False, "reason": "used"}
    try:
        expires = _parse_iso_z(row['expires_at']).replace(tzinfo=None)
    except Exception:
        return {"ok": False, "reason": "bad_expiry"}
    if datetime.utcnow() > expires:
        return {"ok": False, "reason": "expired"}

    stored = (row['token_hash'] or '').encode('utf-8')
    if not stored:
        return {"ok": False, "reason": "not_found"}

    if not bcrypt.checkpw((code or '').strip().encode('utf-8'), stored):
        return {"ok": False, "reason": "invalid"}

    return {"ok": True}


def consume_password_reset_code(user_id: int):
    c = conn()
    c.execute(
        "UPDATE password_reset_tokens SET used_at = ? WHERE user_id = ?",
        (now_iso(), int(user_id)),
    )
    c.commit()


def update_user_password(user_id: int, new_password: str):
    pw_hash = hash_password(new_password)
    c = conn()
    c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, int(user_id)))
    c.commit()


def request_password_reset(full_name: str, company: str, phone: str, chamber_id: int | None, ttl_minutes: int = 20, min_interval_seconds: int = 90):
    """Creates a reset code AND sends it by email.

    For security, if the identity does not match a user, it returns sent=False without revealing anything.
    If the identity matches but email sending cannot be performed, it raises (so the admin sees the problem).
    """
    u = find_user_by_identity(full_name, company, phone, chamber_id)
    if not u:
        return {"sent": False, "user_id": None, "email_masked": None, "reason": "no_match"}
    if not u['is_active'] or u['is_suspended']:
        return {"sent": False, "user_id": int(u['id']), "email_masked": _mask_email(u.get('email')), "reason": "inactive"}

    code_res = create_password_reset_code(int(u['id']), ttl_minutes=ttl_minutes, min_interval_seconds=min_interval_seconds)
    if not code_res.get('ok'):
        return {"sent": False, "user_id": int(u['id']), "email_masked": _mask_email(u.get('email')), "reason": code_res.get('reason')}

    email = u.get("email")
    if not email:
        raise RuntimeError("El usuario coincide, pero no tiene email guardado en el sistema (campo email vacío).")

    if not _mail_is_configured():
        raise RuntimeError(
            "SMTP no configurado en el servidor. En Render definí variables de entorno "
            "CPF_SMTP_HOST, CPF_SMTP_PORT, CPF_SMTP_USER, CPF_SMTP_PASS y CPF_SMTP_FROM (y redeploy)."
        )

    ok = _send_password_reset_code(
        to_email=email,
        person_name=u.get("name") or u.get("full_name") or "",
        code=code_res["code"],
        expires_minutes=int(code_res.get("ttl_minutes", ttl_minutes)),
    )
    if not ok:
        raise RuntimeError("No se pudo enviar el correo de recuperación. Revisá los Logs en Render (SMTP/credenciales).")

    return {
        "sent": True,
        "user_id": int(u['id']),
        "email_masked": _mask_email(email),
        "ttl_minutes": int(code_res.get("ttl_minutes", ttl_minutes)),
    }


def reset_password_with_code(user_id: int, code: str, new_password: str):
    ok, _msg = password_is_valid(new_password)
    if not ok:
        return {"ok": False, "reason": "weak_password"}

    ver = verify_password_reset_code(user_id, code)
    if not ver.get('ok'):
        return ver

    update_user_password(user_id, new_password)
    consume_password_reset_code(user_id)
    return {"ok": True}