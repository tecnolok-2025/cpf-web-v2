import re
import os
import sqlite3
import uuid
import io
import hashlib

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None
from typing import Any, Dict, List, Optional

from db import UPLOAD_DIR, conn, now_iso


def _safe_filename(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name or "archivo"


# -------------------- Cámaras --------------------
def list_chambers() -> List[dict]:
    c = conn()
    rows = c.execute(
        "SELECT id, name, province, city FROM chambers ORDER BY name"
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_chamber(chamber_id: int) -> Optional[dict]:
    c = conn()
    row = c.execute(
        "SELECT id, name, province, city FROM chambers WHERE id=?",
        (int(chamber_id),),
    ).fetchone()
    c.close()
    return dict(row) if row else None


def create_chamber(name: str, location: Optional[str] = None) -> bool:
    name = (name or "").strip()
    if not name:
        return False
    province = None
    city = None
    if location:
        parts = re.split(r"\s*[/-]\s*", location.strip(), maxsplit=1)
        if len(parts) == 2:
            city, province = parts[0].strip() or None, parts[1].strip() or None
        else:
            city = location.strip()

    c = conn()
    cur = c.cursor()
    exists = cur.execute("SELECT 1 FROM chambers WHERE LOWER(name)=LOWER(?)", (name,)).fetchone()
    if exists:
        c.close()
        return False
    cur.execute(
        "INSERT INTO chambers(name, province, city, created_at) VALUES(?,?,?,?)",
        (name, province, city, now_iso()),
    )
    c.commit()
    c.close()
    return True


# -------------------- Requerimientos --------------------
def create_requirement(
    type_: str,
    title: str,
    description: str,
    user_id: int,
    company: str,
    chamber_id: Optional[int] = None,
    location: Optional[str] = None,
    category: Optional[str] = None,
    urgency: str = "Media",
    tags: str = "",
) -> int:
    c = conn()
    cur = c.cursor()
    cur.execute(
        """INSERT INTO requirements(type, title, description, category, urgency, tags, status,
                                     company, location, chamber_id, user_id, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            type_,
            title.strip(),
            description.strip(),
            category,
            urgency,
            (tags or "").strip(),
            "open",
            company.strip(),
            location,
            chamber_id,
            int(user_id),
            now_iso(),
        ),
    )
    req_id = int(cur.lastrowid)
    c.commit()
    c.close()
    return req_id


def update_requirement(
    req_id: int,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    urgency: Optional[str] = None,
    tags: Optional[str] = None,
    status: Optional[str] = None,
) -> None:
    fields = {}
    if title is not None:
        fields["title"] = title.strip()
    if description is not None:
        fields["description"] = description.strip()
    if category is not None:
        fields["category"] = category
    if urgency is not None:
        fields["urgency"] = urgency
    if tags is not None:
        fields["tags"] = (tags or "").strip()
    if status is not None:
        fields["status"] = status

    if not fields:
        return

    fields["updated_at"] = now_iso()

    keys = list(fields.keys())
    sets = ", ".join([f"{k}=?" for k in keys])
    vals = [fields[k] for k in keys] + [int(req_id)]

    c = conn()
    c.execute(f"UPDATE requirements SET {sets} WHERE id=?", vals)
    c.commit()
    c.close()


def get_requirement(req_id: int) -> Optional[dict]:
    c = conn()
    row = c.execute(
        """SELECT r.*, u.name AS user_name, u.email AS user_email, u.phone AS user_phone,
                  ch.name AS chamber_name
             FROM requirements r
             JOIN users u ON u.id = r.user_id
             LEFT JOIN chambers ch ON ch.id = r.chamber_id
             WHERE r.id=?""",
        (int(req_id),),
    ).fetchone()
    c.close()
    return dict(row) if row else None


def search_requirements(
    q: str = "",
    type_: str = "(Todos)",
    status: str = "open",
    chamber_id: Optional[int] = None,
    limit: int = 200,
) -> List[dict]:
    q = (q or "").strip()
    sql = """SELECT r.id, r.type, r.title, r.description, r.category, r.urgency, r.tags,
                    r.status, r.company, r.location, r.chamber_id, r.user_id, r.created_at,
                    ch.name AS chamber_name
             FROM requirements r
             LEFT JOIN chambers ch ON ch.id = r.chamber_id
             WHERE 1=1"""
    params: List[Any] = []

    if status:
        sql += " AND r.status=?"
        params.append(status)

    if type_ and type_ != "(Todos)":
        sql += " AND r.type=?"
        params.append(type_)

    if chamber_id:
        sql += " AND r.chamber_id=?"
        params.append(int(chamber_id))

    if q:
        like = f"%{q.lower()}%"
        sql += """ AND (
                    LOWER(r.title) LIKE ? OR
                    LOWER(r.description) LIKE ? OR
                    LOWER(r.company) LIKE ? OR
                    LOWER(COALESCE(r.tags,'')) LIKE ?
                )"""
        params.extend([like, like, like, like])

    sql += " ORDER BY r.created_at DESC LIMIT ?"
    params.append(int(limit))

    c = conn()
    rows = c.execute(sql, params).fetchall()
    c.close()
    return [dict(r) for r in rows]


def list_user_requirements(user_id: int, limit: int = 200) -> List[dict]:
    c = conn()
    rows = c.execute(
        """SELECT id, type, title, description, category, urgency, tags, status, created_at, updated_at
           FROM requirements
           WHERE user_id=?
           ORDER BY created_at DESC
           LIMIT ?""",
        (int(user_id), int(limit)),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]



MAX_ATTACHMENTS = int(os.getenv("CPF_MAX_ATTACHMENTS", "2"))
# -------------------- Adjuntos --------------------
def save_attachment(
    requirement_id: int,
    uploaded_by_user_id: int,
    filename: str,
    content: bytes,
    mime: Optional[str] = None,
) -> int:
    # --- Seguridad básica en adjuntos (no reemplaza un antivirus) ---
    if content is None or len(content) == 0:
        raise ValueError("Adjunto vacío.")
    try:
        max_mb = int(os.getenv("CPF_MAX_UPLOAD_MB", "50"))
    except Exception:
        max_mb = 50
    if len(content) > max_mb * 1024 * 1024:
        raise ValueError(f"Adjunto demasiado grande (máx {max_mb} MB).")

    safe = _safe_filename(filename)
    ext = os.path.splitext(safe)[1].lower().lstrip(".")
    allowed = {"jpg","jpeg","png","gif","webp","pdf","doc","docx","xls","xlsx"}
    if ext not in allowed:
        raise ValueError("Tipo de archivo no permitido.")

    # Bloquea ejecutables / scripts (mitigación básica)
    head2 = content[:2]
    if head2 in (b"MZ", b"#!"):
        raise ValueError("Archivo potencialmente ejecutable no permitido.")

    # Validación mínima por firma (best-effort)
    head4 = content[:4]
    if ext in {"jpg","jpeg","png","gif","webp"} and Image is not None:
        try:
            img = Image.open(io.BytesIO(content))
            img.verify()
        except Exception:
            raise ValueError("Imagen inválida o corrupta.")
    elif ext == "pdf":
        # algunos PDFs tienen bytes iniciales de whitespace, por eso buscamos en el primer KB
        if b"%PDF" not in content[:1024]:
            raise ValueError("PDF inválido.")
    elif ext in {"docx","xlsx"}:
        if head4 != b"PK\x03\x04":
            raise ValueError("Archivo Office (docx/xlsx) inválido.")
    elif ext in {"doc","xls"}:
        if content[:8] != b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1":
            raise ValueError("Archivo Office (doc/xls) inválido.")

    UPLOAD_DIR.mkdir(exist_ok=True)

    unique = f"r{int(requirement_id)}_{uuid.uuid4().hex}_{safe}"
    stored_path = str((UPLOAD_DIR / unique).as_posix())

    with open(stored_path, "wb") as f:
        f.write(content)

    c = conn()
    cur = c.cursor()
    cur.execute(
        """INSERT INTO attachments(requirement_id, uploaded_by_user_id, filename, stored_path, mime, size, created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (
            int(requirement_id),
            int(uploaded_by_user_id),
            filename,
            stored_path,
            mime,
            len(content) if content is not None else None,
            now_iso(),
        ),
    )
    att_id = int(cur.lastrowid)
    c.commit()
    c.close()
    return att_id


def list_attachments(requirement_id: int) -> List[dict]:
    c = conn()
    rows = c.execute(
        """SELECT id, filename, stored_path, mime, size, created_at, uploaded_by_user_id
           FROM attachments
           WHERE requirement_id=?
           ORDER BY created_at ASC""",
        (int(requirement_id),),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def read_attachment_bytes(attachment_id: int) -> Optional[bytes]:
    """Devuelve el contenido (bytes) del archivo adjunto.

    Lee desde disco usando el stored_path. Si el archivo ya no existe, devuelve None.
    """
    c = conn()
    row = c.execute(
        "SELECT stored_path FROM attachments WHERE id=?",
        (attachment_id,),
    ).fetchone()
    c.close()
    if not row:
        return None
    path = row["stored_path"] if isinstance(row, sqlite3.Row) else row[0]
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None


def delete_attachment(attachment_id: int, requester_user_id: int, is_superadmin: bool = False) -> bool:
    """Elimina un adjunto si el usuario tiene permiso.

    Permisos:
    - SuperAdmin: siempre.
    - Dueño de la publicación (requirements.user_id): sí.
    """
    c = conn()
    row = c.execute(
        """
        SELECT a.id, a.stored_path, r.user_id AS owner_id
        FROM attachments a
        JOIN requirements r ON r.id = a.requirement_id
        WHERE a.id=?
        """,
        (attachment_id,),
    ).fetchone()
    if not row:
        c.close()
        return False

    owner_id = row["owner_id"]
    stored_path = row["stored_path"]
    if (not is_superadmin) and (owner_id != requester_user_id):
        c.close()
        return False

    c.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
    c.commit()
    c.close()

    try:
        if stored_path and os.path.exists(stored_path):
            os.remove(stored_path)
    except Exception:
        pass
    return True

def _is_image_filename(filename: str) -> bool:
    fn = (filename or "").lower()
    return fn.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))


def _is_image_mime(mime: Optional[str]) -> bool:
    m = (mime or "").lower().strip()
    return m.startswith("image/")


def get_cover_image_bytes(requirement_id: int) -> Optional[Dict[str, Any]]:
    """Devuelve dict con bytes de la primera imagen encontrada entre los adjuntos.

    Regla: se toma el primer adjunto (por created_at ASC) que sea imagen (mime o extensión).
    Devuelve: {"bytes":..., "mime":..., "filename":..., "attachment_id":...}
    """
    atts = list_attachments(int(requirement_id))
    for a in atts:
        fname = a.get("filename") or ""
        mime = a.get("mime") or a.get("mime_type")
        if _is_image_mime(mime) or _is_image_filename(fname):
            data = read_attachment_bytes(int(a["id"]))
            if data:
                return {
                    "bytes": data,
                    "mime": mime or "image/jpeg",
                    "filename": fname,
                    "attachment_id": int(a["id"]),
                }
    return None


def add_attachments(requirement_id: int, files, uploaded_by_user_id: int) -> int:
    """Agrega múltiples adjuntos desde st.file_uploader (UploadedFile list).
    Devuelve cantidad guardada.
    """
    if not files:
        return 0

    existing = list_attachments(int(requirement_id))
    if existing and (len(existing) + len(files) > MAX_ATTACHMENTS):
        raise ValueError(f"Máximo {MAX_ATTACHMENTS} adjuntos por publicación.")
    if len(files) > MAX_ATTACHMENTS:
        raise ValueError(f"Máximo {MAX_ATTACHMENTS} adjuntos por publicación.")

    count = 0
    for f in files:
        try:
            content = f.getvalue() if hasattr(f, "getvalue") else bytes(f)
            save_attachment(
                requirement_id=int(requirement_id),
                uploaded_by_user_id=int(uploaded_by_user_id),
                filename=getattr(f, "name", "archivo"),
                content=content,
                mime=getattr(f, "type", None),
            )
            count += 1
        except Exception:
            # dejamos que el caller muestre warning si quiere
            continue
    return count

# -------------------- Solicitudes de contacto --------------------
def create_contact_request(from_user_id: int, to_user_id: int, requirement_id: int) -> int:
    # Hard safety: avoid self-requests (pueden aparecer por datos legacy/migrados)
    if int(from_user_id) == int(to_user_id):
        raise ValueError("No podés solicitar contacto a vos mismo")

    c = conn()
    cur = c.cursor()

    existing = cur.execute(
        """SELECT id FROM contact_requests
           WHERE from_user_id=? AND to_user_id=? AND requirement_id=? AND status='pending'""",
        (int(from_user_id), int(to_user_id), int(requirement_id)),
    ).fetchone()
    if existing:
        c.close()
        return int(existing["id"])

    cur.execute(
        """INSERT INTO contact_requests(from_user_id, to_user_id, requirement_id, status, created_at)
           VALUES(?,?,?,?,?)""",
        (int(from_user_id), int(to_user_id), int(requirement_id), "pending", now_iso()),
    )
    rid = int(cur.lastrowid)
    c.commit()
    c.close()
    return rid


def list_inbox(user_id: int, status: Optional[str] = "pending", limit: int = 200) -> List[dict]:
    """Solicitudes de contacto recibidas por el usuario (dueño del requerimiento).

    - status='pending' / 'accepted' / 'declined'
    - status=None o 'all' => devuelve todas
    """
    c = conn()
    sql = """SELECT cr.id, cr.status, cr.created_at, cr.responded_at,
                  r.id AS requirement_id, r.title, r.type, r.company,
                  uf.id AS from_user_id, uf.name AS from_name, uf.email AS from_email, uf.phone AS from_phone, uf.company AS from_company,
                  ut.id AS to_user_id, ut.name AS to_name, ut.email AS to_email, ut.phone AS to_phone, ut.company AS to_company
           FROM contact_requests cr
           JOIN requirements r ON r.id = cr.requirement_id
           JOIN users uf ON uf.id = cr.from_user_id
           JOIN users ut ON ut.id = cr.to_user_id
           WHERE cr.to_user_id=?"""
    params: List[Any] = [int(user_id)]

    if status and str(status).lower() not in ("all", "(todos)", "todos"):
        sql += " AND cr.status=?"
        params.append(str(status))

    sql += " ORDER BY cr.created_at DESC LIMIT ?"
    params.append(int(limit))

    rows = c.execute(sql, params).fetchall()
    c.close()
    return [dict(r) for r in rows]


def list_outbox(user_id: int, status: Optional[str] = "pending", limit: int = 200) -> List[dict]:
    """Solicitudes de contacto ENVIADAS por el usuario.

    Útil para que el usuario vea a quién le pidió contacto y si le aceptaron.
    - status='pending' / 'accepted' / 'declined'
    - status=None o 'all' => devuelve todas
    """
    c = conn()
    sql = """SELECT cr.id, cr.status, cr.created_at, cr.responded_at,
                  r.id AS requirement_id, r.title, r.type, r.company,
                  uf.id AS from_user_id, uf.name AS from_name, uf.email AS from_email, uf.phone AS from_phone, uf.company AS from_company,
                  ut.id AS to_user_id, ut.name AS to_name, ut.email AS to_email, ut.phone AS to_phone, ut.company AS to_company
           FROM contact_requests cr
           JOIN requirements r ON r.id = cr.requirement_id
           JOIN users uf ON uf.id = cr.from_user_id
           JOIN users ut ON ut.id = cr.to_user_id
           WHERE cr.from_user_id=?"""
    params: List[Any] = [int(user_id)]

    if status and str(status).lower() not in ("all", "(todos)", "todos"):
        sql += " AND cr.status=?"
        params.append(str(status))

    sql += " ORDER BY cr.created_at DESC LIMIT ?"
    params.append(int(limit))

    rows = c.execute(sql, params).fetchall()
    c.close()
    return [dict(r) for r in rows]


def respond_contact_request(request_id: int, status: str) -> None:
    if status not in ("accepted", "declined"):
        raise ValueError("status inválido")
    c = conn()
    c.execute(
        "UPDATE contact_requests SET status=?, responded_at=? WHERE id=?",
        (status, now_iso(), int(request_id)),
    )
    c.commit()
    c.close()


# -------------------- Métricas --------------------
def admin_metrics() -> Dict[str, Any]:
    """Métricas globales del sistema (sin datos personales).

    Nota: se usa tanto en la vista pública como en el panel logueado.
    Mantener consistencia entre pantallas.
    """
    c = conn()
    cur = c.cursor()

    users = cur.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    chambers = cur.execute("SELECT COUNT(*) AS n FROM chambers").fetchone()["n"]

    # Requerimientos: total histórico vs activos (open)
    reqs_total = cur.execute("SELECT COUNT(*) AS n FROM requirements").fetchone()["n"]
    open_reqs = cur.execute(
        "SELECT COUNT(*) AS n FROM requirements WHERE status='open'"
    ).fetchone()["n"]

    # Solicitudes de contacto
    contacts_pending = cur.execute(
        "SELECT COUNT(*) AS n FROM contact_requests WHERE status='pending'"
    ).fetchone()["n"]
    contacts_accepted = cur.execute(
        "SELECT COUNT(*) AS n FROM contact_requests WHERE status='accepted'"
    ).fetchone()["n"]
    contacts_declined = cur.execute(
        "SELECT COUNT(*) AS n FROM contact_requests WHERE status='declined'"
    ).fetchone()["n"]

    by_ch = cur.execute(
        """SELECT COALESCE(ch.name,'(Sin cámara)') AS chamber,
                  COUNT(r.id) AS total
           FROM requirements r
           LEFT JOIN chambers ch ON ch.id = r.chamber_id
           GROUP BY COALESCE(ch.name,'(Sin cámara)')
           ORDER BY total DESC"""
    ).fetchall()

    c.close()
    return {
        "users": int(users),
        "chambers": int(chambers),
        "requirements": int(reqs_total),
        "open_requirements": int(open_reqs),
        "contacts_pending": int(contacts_pending),
        "contacts_accepted": int(contacts_accepted),
        "contacts_declined": int(contacts_declined),
        "requirements_by_chamber": [dict(r) for r in by_ch],
    }


# -------------------- User approval (Super Admin) --------------------

def list_pending_users(limit: int = 200) -> List[dict]:
    c = conn()
    rows = c.execute(
        """SELECT id, email, name, company, phone, role, created_at
               FROM users
              WHERE is_active=1 AND COALESCE(is_approved,1)=0
              ORDER BY created_at DESC
              LIMIT ?""",
        (int(limit),),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def list_pending_users_by_chamber(chamber_id: int, limit: int = 200) -> List[dict]:
    """Usuarios pendientes de validación para una cámara.

    Usado por rol "assistant" (moderador de cámara). No incluye asistentes.
    """
    c = conn()
    rows = c.execute(
        """SELECT u.id, u.email, u.name, u.company, u.phone, u.role, u.created_at,
                  ch.name AS chamber_name
               FROM users u
               LEFT JOIN chambers ch ON ch.id = u.chamber_id
              WHERE u.is_active=1
                AND COALESCE(u.is_approved,1)=0
                AND u.chamber_id=?
                AND LOWER(COALESCE(u.role,'user')) <> 'assistant'
              ORDER BY datetime(u.created_at) DESC, u.id DESC
              LIMIT ?""",
        (int(chamber_id), int(limit)),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def list_active_approved_users_by_chamber(chamber_id: int, limit: int = 500) -> List[dict]:
    """Usuarios aprobados/activos de una cámara (excluye asistentes)."""
    c = conn()
    rows = c.execute(
        """SELECT u.id, u.email, u.name, u.company, u.phone, u.role,
                  COALESCE(u.is_approved,1) AS is_approved,
                  u.approved_at,
                  u.created_at,
                  ch.name AS chamber_name
               FROM users u
               LEFT JOIN chambers ch ON ch.id = u.chamber_id
              WHERE u.is_active=1
                AND COALESCE(u.is_approved,1)=1
                AND u.chamber_id=?
                AND LOWER(COALESCE(u.role,'user')) <> 'assistant'
              ORDER BY lower(COALESCE(u.company,'')) ASC, lower(COALESCE(u.name,'')) ASC
              LIMIT ?""",
        (int(chamber_id), int(limit)),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def approve_user_scoped(user_id: int, *, chamber_id: int, approved_by_user_id: Optional[int] = None) -> None:
    """Aprueba un usuario validando pertenencia a cámara.

    Usado por asistentes: evita aprobar usuarios fuera de su cámara.
    """
    c = conn()
    row = c.execute(
        "SELECT id, chamber_id, role, is_active, COALESCE(is_approved,1) AS is_approved FROM users WHERE id=?",
        (int(user_id),),
    ).fetchone()
    if not row:
        c.close()
        raise ValueError("Usuario inexistente")
    d = dict(row)
    if int(d.get("is_active") or 0) != 1:
        c.close()
        raise ValueError("Usuario inactivo")
    if int(d.get("chamber_id") or 0) != int(chamber_id):
        c.close()
        raise ValueError("No tenés permisos para validar usuarios de otra cámara")
    if str(d.get("role") or "user").strip().lower() == "assistant":
        c.close()
        raise ValueError("No se pueden aprobar asistentes desde este panel")
    # idempotente
    c.execute(
        """UPDATE users
               SET is_approved=1,
                   approved_at=?,
                   approved_by=?
             WHERE id=?""",
        (now_iso(), approved_by_user_id, int(user_id)),
    )
    c.commit()
    c.close()


def reject_user_scoped(user_id: int, *, chamber_id: int, rejected_by_user_id: Optional[int] = None) -> None:
    """Rechaza (desactiva) un usuario validando pertenencia a cámara."""
    c = conn()
    row = c.execute(
        "SELECT id, chamber_id, role FROM users WHERE id=?",
        (int(user_id),),
    ).fetchone()
    if not row:
        c.close()
        raise ValueError("Usuario inexistente")
    d = dict(row)
    if int(d.get("chamber_id") or 0) != int(chamber_id):
        c.close()
        raise ValueError("No tenés permisos para moderar usuarios de otra cámara")
    if str(d.get("role") or "user").strip().lower() == "assistant":
        c.close()
        raise ValueError("No se pueden rechazar asistentes desde este panel")

    c.execute("UPDATE users SET is_active=0 WHERE id=?", (int(user_id),))
    c.commit()
    c.close()


def chamber_metrics(chamber_id: int) -> Dict[str, Any]:
    """Métricas resumidas por cámara (para rol assistant)."""
    c = conn()
    cur = c.cursor()

    open_reqs = cur.execute(
        "SELECT COUNT(*) AS n FROM requirements WHERE status='open' AND chamber_id=?",
        (int(chamber_id),),
    ).fetchone()["n"]

    pending_users = cur.execute(
        """SELECT COUNT(*) AS n
             FROM users
            WHERE is_active=1
              AND COALESCE(is_approved,1)=0
              AND chamber_id=?
              AND LOWER(COALESCE(role,'user')) <> 'assistant'""",
        (int(chamber_id),),
    ).fetchone()["n"]

    approved_users = cur.execute(
        """SELECT COUNT(*) AS n
             FROM users
            WHERE is_active=1
              AND COALESCE(is_approved,1)=1
              AND chamber_id=?
              AND LOWER(COALESCE(role,'user')) <> 'assistant'""",
        (int(chamber_id),),
    ).fetchone()["n"]

    c.close()
    return {
        "open_requirements": int(open_reqs),
        "pending_users": int(pending_users),
        "approved_users": int(approved_users),
    }


def assistant_update_pending_user(
    user_id: int,
    *,
    chamber_id: int,
    name: Optional[str] = None,
    company: Optional[str] = None,
    phone: Optional[str] = None,
) -> None:
    """Permite a un asistente corregir datos básicos de un usuario pendiente.

    Solo opera sobre usuarios de su cámara, activos y no aprobados.
    """
    c = conn()
    row = c.execute(
        """SELECT id, chamber_id, is_active, COALESCE(is_approved,1) AS is_approved, role
             FROM users WHERE id=?""",
        (int(user_id),),
    ).fetchone()
    if not row:
        c.close()
        raise ValueError("Usuario inexistente")
    d = dict(row)
    if int(d.get("chamber_id") or 0) != int(chamber_id):
        c.close()
        raise ValueError("No tenés permisos para editar usuarios de otra cámara")
    if int(d.get("is_active") or 0) != 1:
        c.close()
        raise ValueError("Usuario inactivo")
    if int(d.get("is_approved") or 0) == 1:
        c.close()
        raise ValueError("El usuario ya fue aprobado")
    if str(d.get("role") or "user").strip().lower() == "assistant":
        c.close()
        raise ValueError("No se pueden editar asistentes desde este panel")

    fields = {}
    if name is not None:
        nm = (name or "").strip()
        if not nm:
            c.close()
            raise ValueError("Nombre vacío")
        fields["name"] = nm
        fields["full_name"] = nm
    if company is not None:
        fields["company"] = (company or "").strip() or None
    if phone is not None:
        ph = (phone or "").strip()
        if not ph:
            c.close()
            raise ValueError("Teléfono vacío")
        fields["phone"] = ph

    if not fields:
        c.close()
        return

    keys = list(fields.keys())
    sets = ", ".join([f"{k}=?" for k in keys])
    vals = [fields[k] for k in keys] + [int(user_id)]
    c.execute(f"UPDATE users SET {sets} WHERE id=?", vals)
    c.commit()
    c.close()


def approve_user(user_id: int, approved_by_user_id: Optional[int] = None) -> None:
    c = conn()
    c.execute(
        """UPDATE users
               SET is_approved=1,
                   approved_at=?,
                   approved_by=?
             WHERE id=?""",
        (now_iso(), approved_by_user_id, int(user_id)),
    )
    c.commit()
    c.close()


def reject_user(user_id: int, rejected_by_user_id: Optional[int] = None) -> None:
    # Rechazo simple: desactivar cuenta (no se borra para auditoría)
    c = conn()
    c.execute(
        """UPDATE users
               SET is_active=0
             WHERE id=?""",
        (int(user_id),),
    )
    c.commit()
    c.close()


def list_admin_users(limit: int = 500) -> List[dict]:
    """Lista admins (incluye estado: activo/suspendido)."""
    c = conn()
    rows = c.execute(
        """SELECT id, email, name, company, phone, role, is_active,
                  COALESCE(is_approved,1) AS is_approved,
                  COALESCE(is_suspended,0) AS is_suspended,
                  created_at, approved_at
             FROM users
            WHERE role='admin'
            ORDER BY created_at DESC
            LIMIT ?""",
        (int(limit),),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def set_user_suspended(user_id: int, suspended: bool, by_user_id: Optional[int] = None) -> None:
    c = conn()
    c.execute(
        """UPDATE users
              SET is_suspended=?,
                  suspended_at=?,
                  suspended_by=?
            WHERE id=?""",
        (1 if suspended else 0, now_iso() if suspended else None, by_user_id, int(user_id)),
    )
    c.commit()
    c.close()


def deactivate_user(user_id: int) -> None:
    """Anula (desactiva) usuario, sin borrar."""
    c = conn()
    c.execute("UPDATE users SET is_active=0 WHERE id=?", (int(user_id),))
    c.commit()
    c.close()


def list_users(query: str | None = None):
    """Lista usuarios (vista admin/super admin). No expone password_hash."""
    c = conn()
    q = (query or "").strip().lower()
    sql = """
        SELECT 
            u.id, u.email, u.name, u.company, u.phone,
            u.role, u.is_active,
            COALESCE(u.is_approved, 1) AS is_approved,
            u.approved_at,
            COALESCE(u.is_suspended, 0) AS is_suspended,
            u.suspended_at,
            u.created_at,
            u.chamber_id,
            ch.name AS chamber_name
        FROM users u
        LEFT JOIN chambers ch ON ch.id = u.chamber_id
    """
    params = ()
    if q:
        sql += """ WHERE lower(u.email) LIKE ? OR lower(u.name) LIKE ? OR lower(COALESCE(u.company,'')) LIKE ? """
        like = f"%{q}%"
        params = (like, like, like)
    sql += " ORDER BY datetime(u.created_at) DESC, u.id DESC"
    rows = c.execute(sql, params).fetchall()
    c.close()
    out = []
    for r in rows:
        d = dict(r)
        # normalizaciones
        d["is_active"] = int(d.get("is_active", 0) or 0)
        d["is_approved"] = int(d.get("is_approved", 0) or 0)
        d["is_suspended"] = int(d.get("is_suspended", 0) or 0)
        out.append(d)
    return out


# -------------------- Super Admin: edición rápida (tablas) --------------------
def update_user_superadmin(
    user_id: int,
    **fields,
) -> None:
    """Actualiza campos administrativos de un usuario.

    Diseñado para correcciones rápidas desde la grilla (solo Super Admin en la UI).
    No toca password_hash.
    """
    allowed = {"email", "name", "company", "phone", "chamber_id", "role", "is_active", "is_approved", "approved_at"}
    f = {k: fields.get(k) for k in fields.keys() if k in allowed}
    if not f:
        return

    # Normalizaciones / validaciones mínimas
    if "email" in f:
        email = (f.get("email") or "").strip().lower()
        if not email or "@" not in email:
            raise ValueError("email inválido")
        f["email"] = email

    if "name" in f:
        name = (f.get("name") or "").strip()
        if not name:
            raise ValueError("nombre vacío")
        f["name"] = name

    if "chamber_id" in f:
        ch = f.get("chamber_id")
        # permitir limpiar con valores vacíos
        if ch is None:
            f["chamber_id"] = None
        else:
            try:
                # aceptar strings vacíos como NULL
                if isinstance(ch, str) and ch.strip() == "":
                    f["chamber_id"] = None
                else:
                    ch_int = int(ch)
                    # Validar existencia
                    c2 = conn()
                    ok = c2.execute("SELECT 1 FROM chambers WHERE id=?", (ch_int,)).fetchone()
                    c2.close()
                    if not ok:
                        raise ValueError(f"chamber_id inexistente ({ch_int})")
                    f["chamber_id"] = ch_int
            except ValueError:
                raise
            except Exception:
                raise ValueError("chamber_id inválido")

    if "company" in f:
        comp = (f.get("company") or "").strip()
        f["company"] = comp if comp else None

    if "phone" in f:
        ph = (f.get("phone") or "").strip()
        f["phone"] = ph if ph else None

    if "role" in f:
        role = (f.get("role") or "user").strip().lower()
        if role not in {"user", "admin", "assistant"}:
            raise ValueError("role inválido")
        f["role"] = role

    if "is_active" in f:
        f["is_active"] = 1 if int(f.get("is_active") or 0) == 1 else 0

    if "is_approved" in f:
        f["is_approved"] = 1 if int(f.get("is_approved") or 0) == 1 else 0

    # Coherencia is_approved / approved_at
    if f.get("is_approved") == 0:
        f["approved_at"] = None
    elif f.get("is_approved") == 1 and "approved_at" in f:
        # si viene vacío, lo dejamos como NULL (la UI suele completar), pero no forzamos acá.
        val = (f.get("approved_at") or "").strip() if isinstance(f.get("approved_at"), str) else f.get("approved_at")
        f["approved_at"] = val if val else None

    keys = list(f.keys())
    sets = ", ".join([f"{k}=?" for k in keys])
    vals = [f[k] for k in keys] + [int(user_id)]

    c = conn()
    try:
        c.execute(f"UPDATE users SET {sets} WHERE id=?", vals)
        c.commit()
    finally:
        c.close()


def update_chamber_superadmin(
    chamber_id: int,
    **fields,
) -> None:
    """Actualiza datos de una cámara (solo Super Admin en la UI)."""
    allowed = {"name", "province", "city"}
    f = {k: fields.get(k) for k in fields.keys() if k in allowed}
    if not f:
        return

    if "name" in f:
        nm = (f.get("name") or "").strip()
        if not nm:
            raise ValueError("nombre vacío")
        f["name"] = nm

    if "province" in f:
        prov = (f.get("province") or "").strip()
        f["province"] = prov if prov else None

    if "city" in f:
        city = (f.get("city") or "").strip()
        f["city"] = city if city else None

    keys = list(f.keys())
    sets = ", ".join([f"{k}=?" for k in keys])
    vals = [f[k] for k in keys] + [int(chamber_id)]

    c = conn()
    try:
        c.execute(f"UPDATE chambers SET {sets} WHERE id=?", vals)
        c.commit()
    finally:
        c.close()
