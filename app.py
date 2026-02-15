import streamlit as st
from mailer import mailer_is_configured
import re
import os
import base64
def _fixed_manual_and_exit_controls():
    """Botón fijo (arriba derecha) para descargar el Manual (vista pública)."""
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    pdf_path = os.path.join(assets_dir, "manual_usuario_cpf.pdf")
    icon_path = os.path.join(assets_dir, "manual_icon.png")

    pdf_b64 = None
    try:
        with open(pdf_path, "rb") as f:
            pdf_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        pdf_b64 = None

    icon_b64 = None
    try:
        with open(icon_path, "rb") as f:
            icon_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        icon_b64 = None

    # Link "data:" para descargar/abrir el PDF
    manual_link = "#"
    if pdf_b64:
        manual_link = f"data:application/pdf;base64,{pdf_b64}"

    icon_html = ""
    if icon_b64:
        icon_html = (
            f"<img src='data:image/png;base64,{icon_b64}' "
            "style='height:22px;width:auto;margin-right:10px;vertical-align:middle;' />"
        )

    # UI fija: más prolija, tipo “pill”, con hover suave.
    st.markdown(
        f"""
<style>
.cpf-fixed-actions {{
  position: fixed;
  top: 12px;
  right: 12px;
  z-index: 999999;
  display: flex;
  align-items: center;
}}
.cpf-pill {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid rgba(11,77,176,0.25);
  background: rgba(255,255,255,0.92);
  backdrop-filter: blur(6px);
  color: #0B4DB0;
  font-weight: 800;
  text-decoration: none;
  box-shadow: 0 6px 18px rgba(0,0,0,0.10);
  transition: transform .08s ease, box-shadow .12s ease, background .12s ease;
}}
.cpf-pill:hover {{
  transform: translateY(-1px);
  background: rgba(255,255,255,1);
  box-shadow: 0 10px 22px rgba(0,0,0,0.14);
}}
.cpf-pill:active {{
  transform: translateY(0px);
}}
.cpf-pill small {{
  font-weight: 700;
  opacity: 0.8;
}}
@media (max-width: 640px) {{
  .cpf-fixed-actions {{ top: 8px; right: 8px; }}
  .cpf-pill {{ padding: 9px 12px; }}
}}
</style>

<div class="cpf-fixed-actions">
  <a class="cpf-pill" href="{manual_link}" download="Manual_CPF.pdf" target="_blank" rel="noopener">
    {icon_html}<span>Manual</span><small>PDF</small>
  </a>
</div>
""",
        unsafe_allow_html=True,
    )

from pathlib import Path
import shutil


# -------------------- UI enums (defensivo) --------------------
# Estos valores son *opcionales* y solo alimentan combos en la UI.
# La app NO depende de que existan categorías específicas.
# Nota: "(Sin categoría)" ya se agrega como opción placeholder en la UI.
# Por eso NO incluimos "Sin categoría" acá (evita duplicados en el combo).
CATEGORIES = [
    "Servicios",
    "Insumos",
    "Fabricación",
    "Mantenimiento",
    "Logística",
    "Tecnología",
    "Energía",
    "RRHH",
    "Otros",
]

URGENCY = [
    "baja",
    "media",
    "alta",
    "urgente",
]

# -------------------- Revisión 27: reglas de completitud y portada --------------------
IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp"}
REQUIRE_COVER_IMAGE = True  # obliga que el adjunto 1 sea una imagen portada
REQUIRE_CATEGORY = True     # obliga seleccionar categoría (no "Sin categoría")
REQUIRE_LOCATION = True     # obliga completar ubicación
MAX_ATTACHMENTS = int(os.getenv("CPF_MAX_ATTACHMENTS", "2"))

# Revisión 29 (hotfix): marcador de versión para verificar despliegues
APP_REV = "50"



# -------------------- Branding (Revisión 28) --------------------
def _render_sidebar_logo():
    """Muestra el logo CPF dentro de la barra lateral (no fijo)."""
    try:
        base = Path(__file__).resolve().parent
        candidates = []

        env_path = (os.getenv("CPF_LOGO_PATH") or "").strip()
        if env_path:
            candidates.append(Path(env_path))

        candidates += [
            base / "assets" / "cpf_logo.png",
            base / "assets" / "Logo sistemas de requerimientos.png",
            base / "cpf_logo.png",
        ]

        p = next((c for c in candidates if c.exists()), None)
        if not p:
            return

        # +30% aprox: ocupar el ancho disponible de la barra lateral
        st.image(str(p), use_container_width=True)
        st.markdown("---")
    except Exception:
        # no bloquea la app
        return



def _disk_usage_pie(mount_path: str):
    """Grafico circular (ocupado vs libre). Visible SOLO para Admin (no Super Admin)."""
    try:
        import matplotlib.pyplot as plt
        usage = shutil.disk_usage(mount_path)
        total = float(usage.total)
        used = float(usage.used)
        free = float(usage.free)
        if total <= 0:
            return

        pct = (used / total) * 100.0
        gb = 1024 ** 3
        used_gb = used / gb
        free_gb = free / gb
        total_gb = total / gb

        st.caption(f"Disco: {mount_path} — {used_gb:.2f} GB usados / {total_gb:.2f} GB (libre: {free_gb:.2f} GB)")
        fig, ax = plt.subplots(figsize=(3.2, 3.2))
        ax.pie(
            [used, free],
            labels=["Ocupado", "Libre"],
            colors=["#d7263d", "#1b998b"],  # rojo / verde
            autopct=lambda p: f"{p:.0f}%",
            startangle=90,
            counterclock=False,
            textprops={"fontsize": 10},
        )
        ax.set_title(f"Ocupación: {pct:.0f}%")
        ax.axis("equal")
        st.pyplot(fig, use_container_width=False)
    except Exception as e:
        st.caption(f"No se pudo leer el uso de disco: {e}")


def _uget(u, key, default=None):
    """Lee un campo de usuario soportando dict o sqlite3.Row."""
    if u is None:
        return default
    try:
        if hasattr(u, "get"):
            return u.get(key, default)
    except Exception:
        pass
    try:
        return u[key]
    except Exception:
        try:
            return dict(u).get(key, default)
        except Exception:
            return default
def _norm_text(s: str) -> str:
    import unicodedata
    s = s or ""
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return s.casefold()

# Lista MUY acotada de insultos graves (evitamos falsos positivos).
# Si necesitás ampliarla, lo hacemos con criterio y pruebas.
_OFFENSIVE_WORDS = [
    "pelotudo", "pelotuda",
    "boludo", "boluda",
    "idiota",
    "imbecil", "imbécil",
    "puto", "puta",
    "mierda",
]

def detect_offensive_words(text: str):
    """Devuelve lista de coincidencias: [{'word':..., 'start':..., 'end':...}]"""
    t = text or ""
    nt = _norm_text(t)
    matches = []
    for w in _OFFENSIVE_WORDS:
        nw = _norm_text(w)
        # buscar como palabra completa (bordes no alfanuméricos)
        for m in re.finditer(rf"(?<![\w]){re.escape(nw)}(?![\w])", nt):
            matches.append({"word": w, "start": m.start(), "end": m.end()})
    # ordenar y deduplicar por rango
    matches = sorted(matches, key=lambda x: (x["start"], x["end"]))
    dedup = []
    last_end = -1
    for mm in matches:
        if mm["start"] >= last_end:
            dedup.append(mm)
            last_end = mm["end"]
    return dedup

def highlight_offensive(text: str, matches):
    """Devuelve HTML con <mark> para mostrar dónde está el problema."""
    if not matches:
        return text
    t = text or ""
    # Como matches están sobre texto normalizado, hacemos highlight aproximado:
    # reconstruimos por búsqueda sobre original con normalización por ventanas.
    nt = _norm_text(t)
    spans = [(m["start"], m["end"]) for m in matches]
    out = []
    last = 0
    for s,e in spans:
        out.append(t[last:s])
        out.append(f"<mark>{t[s:e]}</mark>")
        last = e
    out.append(t[last:])
    return "".join(out)
import pandas as pd
import datetime
from pathlib import Path

import services as svc
import mailer
from db import (
    conn as db_conn,
    now_iso,
    backup_db,
    backup_full,
    list_full_backups,
    get_last_full_backup_path,
    restore_full_from_zip_path,
    list_backups,
    get_backup_dir,
    set_backup_dir,
    get_last_backup_path,
    restore_db_from_path,
    get_super_admin_email,  # legacy
    get_super_admin_emails,
    add_super_admin_email,
    remove_super_admin_email,
)

from auth import any_admin_exists, create_user, authenticate, is_super_admin, get_user_by_email

try:
    from ai import assistant_answer, review_requirement
except Exception:
    def assistant_answer(q: str, role: str = "user"):
        return {"answer": "Asistente IA no disponible (ai.py con error).", "table": None}

    def review_requirement(title: str, description: str):
        """Fallback: revisión simple local sin IA.

        Contrato de salida compatible con el resto de la app:
        - ok: bool
        - reason: str
        - hits: list[str]
        - suggested_title / suggested_description (opcionales)
        """
        text = f"{title}\n{description}".lower()
        bad_words = [
            "idiota", "imbecil", "imbécil", "estupido", "estúpido",
            "pelotudo", "pelotuda", "boludo", "boluda",
            "mierda", "puta", "puto",
        ]
        hits = sorted({w for w in bad_words if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE)})
        if hits:
            return {
                "ok": False,
                "reason": "El texto contiene palabras ofensivas.",
                "hits": hits,
            }
        return {
            "ok": True,
            "reason": "OK",
            "hits": [],
            "suggested_title": title,
            "suggested_description": description,
        }


def _get_user():
    return st.session_state.get("user")


def _maybe_auto_backup(reason: str = "logout"):
    """Backup automático SOLO para Super Admin, al cerrar sesión.

    Nota: en Render Free el disco no es persistente; si querés conservarlo, descargalo
    o usá un disco persistente/plan pago.
    """
    u = st.session_state.get("user")
    if not u:
        return
    if not is_super_admin(_uget(u, 'email', "")):
        return
    if reason != "logout":
        return

    done_key = f"_auto_backup_done_{reason}"
    if st.session_state.get(done_key):
        return

    try:
        # backup_db devuelve un path (str). Guardamos ese path en sesión.
        b_path = backup_db(reason=reason)
        st.session_state["_last_backup"] = b_path
        st.session_state[done_key] = True
    except Exception as e:
        st.session_state["_last_backup_err"] = str(e)


def _backup_download_ui():
    """UI de resguardo (solo Super Admin)."""
    u = st.session_state.get("user")
    if not u or not is_super_admin(_uget(u, 'email', "")):
        return

    emails = get_super_admin_emails()
    st.caption(f"Super Admin(s): {', '.join(emails) if emails else (get_super_admin_email() or '-')}")

    cur_dir = get_backup_dir()
    new_dir = st.text_input(
        "Directorio de backups",
        value=cur_dir,
        help="En PC/local podés elegir cualquier carpeta. En Render el filesystem puede ser efímero salvo disco persistente.",
    )
    if new_dir and new_dir != cur_dir and st.button("Guardar directorio"):
        set_backup_dir(new_dir)
        st.success("Directorio actualizado.")

    def _normalize_backup_obj(obj):
        """Convierte 'obj' a dict con bytes para st.download_button.
        Soporta:
          - str (path) -> lee bytes
          - dict ya armado -> lo deja
        """
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, str):
            try:
                p = Path(obj)
                data = p.read_bytes()
                return {"ok": True, "path": obj, "filename": p.name, "bytes": data}
            except Exception as e:
                return {"ok": False, "path": obj, "error": str(e)}
        return {"ok": False, "error": "tipo de backup no soportado"}


    st.subheader("Backup completo (DB + adjuntos)")
    st.caption("Incluye la base de datos (cpf.db) y la carpeta de adjuntos (uploads/). Ideal para restaurar el sistema completo.")

    if st.button("Crear backup completo ahora (ZIP)", use_container_width=True):
        path_full = backup_full(reason="manual")  # devuelve path (str)
        bfull = _normalize_backup_obj(path_full)
        st.session_state["_last_full_backup"] = bfull
        if bfull and bfull.get("ok"):
            st.success("Backup completo generado.")
        else:
            st.error(f"No pude generar el backup completo: {bfull.get('error') if isinstance(bfull, dict) else 'error desconocido'}")

    bfull = _normalize_backup_obj(st.session_state.get("_last_full_backup"))
    st.session_state["_last_full_backup"] = bfull
    if bfull and bfull.get("ok"):
        st.download_button(
            "Descargar último backup completo (ZIP)",
            data=bfull["bytes"],
            file_name=bfull.get("filename","cpf_full_backup.zip"),
            mime="application/zip",
            use_container_width=True,
        )
    else:
        st.info("Todavía no hay un backup completo generado en esta sesión.")

    st.divider()
    st.subheader("Restaurar backup completo (ZIP) — solo Super Admin")
    fulls = list_full_backups()
    pick_full = st.selectbox(
        "Backups completos locales (ZIP)",
        options=["(ninguno)"] + fulls,
        format_func=lambda p: p if p=="(ninguno)" else Path(p).name,
        key="pick_full_zip",
    )
    up_full = st.file_uploader("O subir un backup completo .zip", type=["zip"], key="up_full_zip")
    if st.button("♻️ Restaurar backup completo", use_container_width=True, key="restore_full_btn"):
        try:
            if up_full is not None:
                tmp_path = Path(get_backup_dir()) / f"uploaded_full_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                tmp_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path.write_bytes(up_full.getvalue())
                restore_full_from_zip_path(str(tmp_path))
                st.success("Restaurado (DB + adjuntos). Recargando…")
                st.rerun()
            elif pick_full and pick_full != "(ninguno)":
                restore_full_from_zip_path(pick_full)
                st.success("Restaurado (DB + adjuntos). Recargando…")
                st.rerun()
            else:
                st.warning("Seleccioná o subí un backup completo .zip.")
        except Exception as e:
            st.error(f"No se pudo restaurar el backup completo: {e}")

    st.divider()
    if st.button("Crear backup ahora"):
        path = backup_db(reason="manual")  # backup_db devuelve path (str)
        b = _normalize_backup_obj(path)
        st.session_state["_last_backup"] = b
        if b and b.get("ok"):
            st.success("Backup generado.")
        else:
            st.error(f"No pude generar el backup: {b.get('error') if isinstance(b, dict) else 'error desconocido'}")

    b = _normalize_backup_obj(st.session_state.get("_last_backup"))
    st.session_state["_last_backup"] = b
    if b and b.get("ok"):
        st.download_button(
            "Descargar último backup (.db)",
            data=b["bytes"],
            file_name=b.get("filename","cpf_backup.db"),
            mime="application/octet-stream",
            use_container_width=True,
        )
    else:
        st.info("Todavía no hay un backup generado en esta sesión.")

    st.divider()
    st.subheader("Restaurar (solo Super Admin)")
    backups = list_backups()
    pick = st.selectbox("Backups locales", options=["(ninguno)"] + backups, format_func=lambda p: p if p=="(ninguno)" else Path(p).name)
    up = st.file_uploader("O subir un backup .db", type=["db"])
    if st.button("♻️ Restaurar ahora", use_container_width=True):
        try:
            if up is not None:
                tmp_path = Path(get_backup_dir()) / f"uploaded_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                tmp_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path.write_bytes(up.getvalue())
                restore_db_from_path(str(tmp_path))
                st.success("Restaurado. Recargando…")
                st.rerun()
            elif pick and pick != "(ninguno)":
                restore_db_from_path(pick)
                st.success("Restaurado. Recargando…")
                st.rerun()
            else:
                st.warning("Seleccioná o subí un backup.")
        except Exception as e:
            st.error(f"No se pudo restaurar: {e}")


def _logout():
    st.session_state.pop("user", None)
    st.rerun()


def _assistant_sidebar(role: str):
    st.divider()
    with st.expander("Asistente IA", expanded=False):
        st.caption("Consultas rápidas sobre el sistema y el contenido (modo local/IA).")
        st.session_state.setdefault("assistant_history", [])
        st.session_state.setdefault("assistant_q", "")

        def _send():
            q = (st.session_state.get("assistant_q") or "").strip()
            if not q:
                return
            out = assistant_answer(q, role=role)
            ans = out.get("answer", "")
            st.session_state["assistant_history"].append({"role": "user", "content": q})
            st.session_state["assistant_history"].append({"role": "assistant", "content": ans})
            st.session_state["assistant_q"] = ""

        st.text_input("Tu pregunta", key="assistant_q", placeholder="Ej: ¿cómo publico? ¿métricas? ¿qué hace la bandeja?")
        st.button("Enviar", on_click=_send, key="assistant_send")

        hist = st.session_state["assistant_history"]
        if hist:
            st.write("---")
            for msg in hist[-6:]:
                if msg["role"] == "user":
                    st.markdown(f"**Vos:** {msg['content']}")
                else:
                    st.markdown(f"**Asistente:** {msg['content']}")


def _login_ui():
    st.subheader("Iniciar sesión")
    with st.form("login_form"):
        email = st.text_input("Correo electrónico")
        password = st.text_input("Contraseña", type="password")
        ok = st.form_submit_button("Ingresar")
        if ok:
            u = authenticate(email, password)
            if isinstance(u, dict) and u.get("_suspended"):
                st.error(
                    "Tu cuenta se encuentra **SUSPENDIDA** por el Super Admin. "
                    "Si considerás que es un error, contactá a la administración."
                )
            elif isinstance(u, dict) and u.get("_pending"):
                st.warning("Tu cuenta está **pendiente de validación** por el moderador/Super Admin. \n\nCuando sea aprobada, vas a poder ingresar con tu email y contraseña.")
            elif u:
                st.session_state["user"] = u
                st.success("Sesión iniciada.")
                st.rerun()
            else:
                st.error("Credenciales inválidas o usuario inactivo.")




def _chamber_id_from_name(chambers, chamber_name):
    """Devuelve el id de la cámara a partir del nombre seleccionado.
    Si el usuario elige un placeholder / '(Sin cámara)' o no hay match, devuelve None.
    """
    if not chamber_name:
        return None
    ch = chamber_name.strip()
    if ch in ['(Sin cámara)', 'Sin cámara', '-- Seleccioná --', '-- Seleccione --', '-- Seleccionar --']:
        return None
    for c in chambers or []:
        if c.get('name') == chamber_name:
            return c.get('id')
    return None

def _register_ui():
    # Panel de registro / recuperación de contraseña (sidebar)
    chambers = svc.list_chambers()
    chamber_names = [c["name"] for c in chambers]

    # Estado de recuperación
    stage = st.session_state.get("pw_reset_stage", "none")  # none | identify | verify

    if stage == "none":
        # --- Registro normal ---
        with st.form("register_form", clear_on_submit=False):
            email = st.text_input("Correo electrónico", key="reg_email")
            pw = st.text_input("Contraseña", type="password", key="reg_pw")
            full_name = st.text_input("Nombre y Apellido", key="reg_name")
            company = st.text_input(
                "Empresa / Asistente",
                key="reg_company",
                help="Si sos personal de una cámara/institución, incluí la palabra 'asistente' (ej: 'UIC - asistente').",
            )
            phone = st.text_input("Teléfono", key="reg_phone")
            if chamber_names:
                chamber_name = st.selectbox(
                    "Cámara o institución",
                    options=["-- Seleccioná --"] + chamber_names,
                    key="reg_chamber",
                )
                chamber_id = _chamber_id_from_name(chambers, chamber_name)
            else:
                st.warning("Aún no hay cámaras/instituciones cargadas. Contactá al administrador para poder registrarte.")
                chamber_id = None

            if st.form_submit_button("Crear usuario"):
                try:
                    if not email or not pw or not full_name or not company or not phone:
                        st.error("Completá Correo, Contraseña, Nombre, Empresa/Asistente y Teléfono.")
                    elif chamber_id is None:
                        st.error("Seleccioná una **Cámara o institución** para poder registrarte.")
                    else:
                        # v49: si el campo Empresa contiene "asistente", registramos como rol assistant
                        comp_norm = (company or "").strip().lower()
                        role_reg = "assistant" if ("asistente" in comp_norm or "assistant" in comp_norm) else "user"
                        create_user(
                            email=email,
                            password=pw,
                            full_name=full_name,
                            company=company,
                            phone=phone,
                            role=role_reg,
                            chamber_id=chamber_id,
                            approved=False,
                        )
                        st.success("✅ Registro recibido.")
                        st.info(
                            "Tu usuario fue **enviado a validación** por el moderador/Super Admin.\n\n"
                            "En cuanto sea aprobado, vas a poder ingresar con tu **email** y tu **contraseña**."
                        )
                except Exception as e:
                    st.error(str(e))

        # Botón fuera del form (Streamlit no permite 2 submit buttons con acciones distintas)

        if st.button("Olvidé mi contraseña"):
            st.session_state["pw_reset_stage"] = "identify"
            # Limpiar restos
            st.session_state.pop("pw_reset_ident", None)
            st.session_state.pop("pw_reset_notice", None)
            st.rerun()

        return

    # --- Recuperación de contraseña ---
    st.markdown("### Recuperar acceso")
    from_addr = (os.getenv("CPF_SMTP_FROM") or os.getenv("SMTP_FROM") or "").strip()
    sender_line = f"El correo saldrá desde: **{from_addr}**." if from_addr else "El correo saldrá desde la casilla de notificaciones configurada en el sistema."
    st.caption(
        "Completá los campos remarcados en rojo. Si los datos coinciden con un usuario registrado, "
        "te enviaremos una **clave provisoria** al correo que quedó guardado en el sistema. "
        + sender_line
    )

    if st.button("Cancelar", key="pw_reset_cancel_top"):
        st.session_state["pw_reset_stage"] = "none"
        st.session_state.pop("pw_reset_ident", None)
        st.session_state.pop("pw_reset_notice", None)
        st.rerun()

    # CSS para resaltar los 4 campos de identificación
    if stage == "identify":
        st.markdown(
            """
            <style>
            /* Resaltado rojo: los campos que usamos para validar identidad */
            input[aria-label="Nombre y Apellido"],
            input[aria-label="Empresa"],
            input[aria-label="Teléfono"] {
                border: 2px solid #d03030 !important;
                border-radius: 8px !important;
                box-shadow: 0 0 0 2px rgba(208, 48, 48, 0.10) !important;
            }
            /* Selectbox (Cámara) */
            div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
                border: 2px solid #d03030 !important;
                border-radius: 8px !important;
                box-shadow: 0 0 0 2px rgba(208, 48, 48, 0.10) !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    notice = st.session_state.get("pw_reset_notice")
    if notice:
        st.info(notice)

    if stage == "identify":
        with st.form("pw_reset_ident_form"):
            # Los dos primeros campos NO se usan en esta etapa
            st.text_input("Correo electrónico", value="(no se usa en recuperación)", disabled=True)
            st.text_input("Contraseña", value="", type="password", disabled=True)

            name = st.text_input("Nombre y Apellido", key="pw_reset_name")
            company = st.text_input("Empresa", key="pw_reset_company")
            phone = st.text_input("Teléfono", key="pw_reset_phone")
            ch = st.selectbox("Cámara o institución", options=["-- Seleccioná --"] + chamber_names, key="pw_reset_ch")

            ok = st.form_submit_button("Enviar clave provisoria")

            if ok:
                chamber_id = _chamber_id_from_name(chambers, ch)

                # Guardar identidad para el paso siguiente
                st.session_state["pw_reset_ident"] = {
                    "name": (name or "").strip(),
                    "company": (company or "").strip(),
                    "phone": (phone or "").strip(),
                    "chamber_id": chamber_id,
                }

                # Validación mínima (evita consultas vacías)
                if (not st.session_state["pw_reset_ident"]["name"]) or (not st.session_state["pw_reset_ident"]["company"]) or (not st.session_state["pw_reset_ident"]["phone"]) or (st.session_state["pw_reset_ident"]["chamber_id"] is None):
                    st.warning("Completá **Nombre y Apellido**, **Empresa**, **Teléfono** y seleccioná tu **Cámara o institución**.")
                else:
                    # No pedimos email: el envío se hace al correo registrado
                    try:
                        from auth import request_password_reset  # import local para evitar ciclos

                        request_password_reset(
                            full_name=st.session_state["pw_reset_ident"]["name"],
                            company=st.session_state["pw_reset_ident"]["company"],
                            phone=st.session_state["pw_reset_ident"]["phone"],
                            chamber_id=st.session_state["pw_reset_ident"]["chamber_id"],
                            ttl_minutes=20,
                            min_interval_seconds=90,
                        )
                    except Exception as e:
                        # Fallo de sistema (SMTP, DB, etc.)
                        st.error(f"No se pudo iniciar la recuperación: {e}")
                        return

                    from_addr2 = (os.getenv("CPF_SMTP_FROM") or os.getenv("SMTP_FROM") or "").strip()
                    sender2 = f"desde **{from_addr2}**" if from_addr2 else "desde la casilla de notificaciones del sistema"
                    st.session_state["pw_reset_notice"] = (
                        "Si los datos coinciden con un usuario registrado, enviamos una **clave provisoria** "
                        f"{sender2} al correo que quedó guardado en el sistema. Revisá también **Spam**."
                    )
                    st.session_state["pw_reset_stage"] = "verify"
                    st.rerun()

    if stage == "verify":
        ident = st.session_state.get("pw_reset_ident") or {}

        with st.form("pw_reset_verify_form"):
            code = st.text_input("Clave provisoria (recibida por email)", key="pw_reset_code")
            new_pw = st.text_input("Nueva contraseña", type="password", key="pw_reset_new_pw")
            new_pw2 = st.text_input("Repetir nueva contraseña", type="password", key="pw_reset_new_pw2")

            ok = st.form_submit_button("Cambiar contraseña")

            if ok:
                if not code.strip():
                    st.warning("Pegá la **clave provisoria** que recibiste por email.")
                    return
                if new_pw != new_pw2:
                    st.warning("Las contraseñas no coinciden.")
                    return

                try:
                    from auth import find_user_by_identity, reset_password_with_code  # import local para evitar ciclos

                    u = find_user_by_identity(
                        full_name=ident.get("name", ""),
                        company=ident.get("company", ""),
                        phone=ident.get("phone", ""),
                        chamber_id=ident.get("chamber_id", None),
                    )

                    if not u:
                        st.error(
                            "No pudimos validar tu identidad con los datos ingresados. "
                            "Volvé al paso anterior y revisá los datos, o contactá al administrador."
                        )
                        return

                    res = reset_password_with_code(
                        user_id=int(u["id"]),
                        code=code.strip(),
                        new_password=new_pw,
                    )

                    if res.get("ok"):
                        st.success("✅ Contraseña actualizada. Ya podés ingresar.")
                        st.session_state["pw_reset_stage"] = "none"
                        st.session_state.pop("pw_reset_ident", None)
                        st.session_state.pop("pw_reset_notice", None)
                        # Limpiar inputs
                        for k in ["pw_reset_code", "pw_reset_new_pw", "pw_reset_new_pw2", "pw_reset_name", "pw_reset_company", "pw_reset_phone", "pw_reset_ch"]:
                            st.session_state.pop(k, None)
                        st.rerun()

                    # Mensajes amigables
                    reason = (res.get("reason") or "").strip()
                    if reason in ("invalid", "not_found", "bad_expiry", "invalid_code", "expired", "used"):
                        st.error("La clave provisoria no es válida o ya expiró. Volvé a pedir una nueva.")
                    elif reason == "weak_password":
                        st.error("La nueva contraseña es débil. Usá al menos 8 caracteres e incluí letras y números.")
                    else:
                        st.error("No se pudo actualizar la contraseña. Intentá nuevamente.")

                except Exception as e:
                    st.error(f"No se pudo actualizar la contraseña: {e}")



def _admin_bootstrap_ui():
    st.info("No existe usuario Admin. Creá el Admin inicial para habilitar el sistema.")

    chambers = svc.list_chambers()
    chamber_names = [c["name"] for c in chambers]

    with st.form("bootstrap_admin"):
        email = st.text_input("Correo electrónico (Administrador)")
        password = st.text_input("Contraseña", type="password")
        name = st.text_input("Nombre y Apellido")
        company = st.text_input("Empresa")
        phone = st.text_input("Teléfono (opcional)")
        ch = st.selectbox("Cámara (opcional)", ["(Sin cámara)"] + chamber_names)
        ok = st.form_submit_button("Crear administrador")

        if ok:
            chamber_id = None
            if ch != "(Sin cámara)":
                for c in chambers:
                    if c["name"] == ch:
                        chamber_id = c["id"]
                        break
            try:
                user_id = create_user(
                    email=email,
                    password=password,
                    full_name=name,
                    company=company,
                    phone=phone or None,
                    role="admin",
                    chamber_id=chamber_id,
                )
                st.session_state["user"] = {
                    "id": user_id,
                    "email": email.strip().lower(),
                    "name": name.strip(),
                    "company": company.strip(),
                    "phone": phone.strip() if phone else None,
                    "role": "admin",
                    "chamber_id": chamber_id,
                    "is_active": 1,
                }
                st.success("Admin creado. Ya estás dentro.")
                st.rerun()
            except Exception as e:
                st.error(str(e))




def _public_panel_home():
    """Pantalla pública (sin login): panel de situación + texto motivacional."""
    _fixed_manual_and_exit_controls()
    st.title("CPF – Sistema de Requerimientos (sin precios)")
    st.caption(
        "Vista pública (solo lectura). Para publicar, solicitar contacto y ver datos completos, "
        "ingresá o registrate desde el menú lateral."
    )

    # Métricas generales (sin datos personales)
    c = db_conn()
    chambers = c.execute("SELECT COUNT(*) AS n FROM chambers").fetchone()["n"]
    open_total = c.execute("SELECT COUNT(*) AS n FROM requirements WHERE status='open'").fetchone()["n"]

    # Compatibilidad de esquema: en DB el campo puede llamarse 'type' (actual) o 'kind' (legacy).
    req_cols = [r["name"] for r in c.execute("PRAGMA table_info(requirements)").fetchall()]
    kind_col = "type" if "type" in req_cols else ("kind" if "kind" in req_cols else None)
    if kind_col:
        open_offers = c.execute(
            f"SELECT COUNT(*) AS n FROM requirements WHERE status='open' AND {kind_col}='offer'"
        ).fetchone()["n"]
        open_needs = c.execute(
            f"SELECT COUNT(*) AS n FROM requirements WHERE status='open' AND {kind_col}='need'"
        ).fetchone()["n"]
    else:
        open_offers = 0
        open_needs = 0
    users_total = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]

    pending = c.execute("SELECT COUNT(*) AS n FROM contact_requests WHERE status='pending'").fetchone()["n"]
    accepted = c.execute("SELECT COUNT(*) AS n FROM contact_requests WHERE status='accepted'").fetchone()["n"]
    rejected = c.execute("SELECT COUNT(*) AS n FROM contact_requests WHERE status='declined'").fetchone()["n"]

    r1 = st.columns(2)
    r1[0].metric("Publicaciones activas", int(open_total))
    r1[1].metric("Usuarios registrados", int(users_total))

    r2 = st.columns(2)
    r2[0].metric("Solicitudes pendientes", int(pending))
    r2[1].metric("Contactos aprobados", int(accepted))

    r3 = st.columns(2)
    r3[0].metric("Cámaras", int(chambers))
    r3[1].metric("Solicitudes rechazadas", int(rejected))

    st.markdown("---")
    st.subheader("Últimas publicaciones activas")
    st.caption("En esta vista no se muestran emails ni teléfonos. Para solicitar contacto, ingresá/registrate.")

    latest = svc.search_requirements(status="open", limit=10)
    if not latest:
        st.info("Todavía no hay publicaciones activas.")
    else:
        for r in latest:
            kind = "OFERTA" if (r.get("type") == "offer" or r.get("kind") == "offer") else "NECESIDAD"
            company = r.get("company") or "(Sin empresa)"
            loc = r.get("location") or "(Sin ubicación)"
            chamber = r.get("chamber_name") or "(Sin cámara)"
            created = r.get("created_at") or ""
            st.markdown(
                f"**{kind}: {r.get('title','(Sin título)')}**  \n"
                f"{company} · {loc} · {chamber}  \n"
                f"Creada: {created}"
            )
    st.markdown("---")
    st.subheader("Cómo funciona")
    st.markdown(
        """
- **Publicás** una **OFERTA** o una **NECESIDAD** (**sin precios** dentro del sistema).
- **Navegás** y **buscás** por palabra clave, empresa, tags o **Cámara/Institución**.
- Si te interesa una publicación, **solicitás contacto**.
- El dueño de la publicación recibe la solicitud en **Bandeja** y **acepta o rechaza**.
- Cuando se acepta, **ambas partes** ven los **datos de contacto** en **Interesados**.
- **Negociación y precios:** se acuerdan **fuera del sistema** (WhatsApp, email, llamada, etc.).

**Registro y acceso (con validación):**
- Al registrarte, debés elegir una **Cámara o institución** (obligatoria) y cargar tu **Teléfono** (obligatorio).
- Tu cuenta queda **pendiente de validación**.
- La validación la realiza el **Asistente** de tu Cámara/Institución (rol *assistant*) o el **Super Admin**.
- Los usuarios *assistant* (personal administrativo) se validan únicamente por **Super Admin**.
- Si tu Cámara/Institución no aparece en la lista, pedí a tu entidad que gestione el **alta** para poder registrarte.

**Roles (resumen):**
- **Empresa/Usuario:** publica, busca, solicita contacto y gestiona sus publicaciones.
- **Asistente (por Cámara/Institución):** valida usuarios **solo** de su cámara (panel único).
- **Super Admin:** administra cámaras, usuarios, moderación/anulación, y backups/restauración.

**Publicaciones y adjuntos:**
- Se solicita **Ubicación** y **Categoría** para ordenar el ecosistema.
- Podés adjuntar **hasta 2 archivos**. Por regla, el **adjunto 1 debe ser una imagen** (JPG/JPEG/PNG/GIF/WEBP) y se usa como **portada**.
- Por seguridad, el sistema acepta solo tipos de archivo permitidos y bloquea ejecutables.

**Recuperar contraseña (“Olvidé mi contraseña”):**
- Hacé clic en **Olvidé mi contraseña** y completá **Nombre y Apellido**, **Empresa**, **Teléfono** y **Cámara/Institución**.
- Si los datos coinciden, recibirás por email una **clave provisoria** (vigencia típica: **20 minutos**).
- Con esa clave, definís tu **nueva contraseña**.
- Revisá también **Spam/No deseado**. Si no llega, contactá a tu Cámara/Institución o al Super Admin.

**Privacidad:** en la vista pública no se muestran teléfonos ni emails.

"""
    )


def _assistant_approval_panel(u: dict):
    """Panel único para rol assistant (moderador por cámara/institución)."""
    st.header("Panel de trabajo (Asistente)")

    chamber_id = u.get("chamber_id")
    if chamber_id is None:
        st.error("Tu usuario no tiene Cámara/Institución asignada. Contactá al Super Admin.")
        return

    ch = svc.get_chamber(int(chamber_id))
    ch_name = (ch.get("name") if ch else None) or "(Sin cámara)"
    st.subheader(f"Cámara / Institución: {ch_name}")

    # Métricas por cámara
    m = svc.chamber_metrics(int(chamber_id))
    r1 = st.columns(3)
    r1[0].metric("Usuarios aprobados", int(m.get("approved_users", 0)))
    r1[1].metric("Pendientes de validación", int(m.get("pending_users", 0)))
    r1[2].metric("Publicaciones activas", int(m.get("open_requirements", 0)))

    st.divider()
    st.subheader("Validar nuevos usuarios")
    st.caption("Solo podés aprobar/rechazar usuarios **de tu cámara**. Los asistentes se validan únicamente por Super Admin.")

    pending = svc.list_pending_users_by_chamber(int(chamber_id), limit=300)
    if not pending:
        st.success("No hay usuarios pendientes en tu cámara.")
    else:
        st.caption(f"Pendientes: {len(pending)}")
        for pu in pending:
            puid = int(pu["id"])
            head = f"#{puid} · {pu.get('email','(sin email)')}"
            with st.expander(head, expanded=False):
                st.write(f"**Registrado por:** {pu.get('name') or '(Sin nombre)'}")
                st.write(f"**Empresa:** {pu.get('company') or '-'}")
                if pu.get("phone"):
                    st.write(f"**Teléfono:** {pu.get('phone')}")
                st.caption(f"Registrado: {pu.get('created_at')}")

                st.markdown("**Correcciones (opcional, antes de aprobar):**")
                nm = st.text_input("Nombre y Apellido", value=pu.get("name") or "", key=f"as_fix_name_{puid}")
                co = st.text_input("Empresa / Asistente", value=pu.get("company") or "", key=f"as_fix_company_{puid}")
                ph = st.text_input("Teléfono", value=pu.get("phone") or "", key=f"as_fix_phone_{puid}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("💾 Guardar", key=f"as_save_{puid}", use_container_width=True):
                        try:
                            svc.assistant_update_pending_user(
                                puid,
                                chamber_id=int(chamber_id),
                                name=nm,
                                company=co,
                                phone=ph,
                            )
                            st.success("Datos actualizados.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                with c2:
                    if st.button("✅ Aprobar", key=f"as_appr_{puid}", use_container_width=True):
                        try:
                            # Intentamos guardar correcciones primero
                            try:
                                svc.assistant_update_pending_user(
                                    puid,
                                    chamber_id=int(chamber_id),
                                    name=nm,
                                    company=co,
                                    phone=ph,
                                )
                            except Exception:
                                pass
                            svc.approve_user_scoped(
                                puid,
                                chamber_id=int(chamber_id),
                                approved_by_user_id=int(u.get("id") or 0) or None,
                            )
                            st.success("Usuario aprobado.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                with c3:
                    if st.button("⛔ Rechazar", key=f"as_rej_{puid}", use_container_width=True):
                        try:
                            svc.reject_user_scoped(
                                puid,
                                chamber_id=int(chamber_id),
                                rejected_by_user_id=int(u.get("id") or 0) or None,
                            )
                            st.warning("Usuario rechazado (cuenta desactivada).")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

    st.divider()
    st.subheader("Usuarios aprobados de tu cámara")
    q = st.text_input("Buscar (email, nombre o empresa)", key="as_q_ok")
    ok_users = svc.list_active_approved_users_by_chamber(int(chamber_id), limit=1000)
    if q:
        qn = q.strip().lower()
        ok_users = [
            r
            for r in ok_users
            if qn in str(r.get("email") or "").lower()
            or qn in str(r.get("name") or "").lower()
            or qn in str(r.get("company") or "").lower()
        ]
    st.caption(f"Total: {len(ok_users)}")
    if ok_users:
        df = pd.DataFrame(ok_users)
        keep = ["id", "email", "name", "company", "phone", "approved_at", "created_at"]
        df = df[[c for c in keep if c in df.columns]].copy()
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Todavía no hay usuarios aprobados en tu cámara.")

    st.info("📱 **Celular:** para registrarte o ingresar, tocá el menú **☰** (arriba a la izquierda) y abrí la sección **Sesión**.\n🖥️ **PC:** la sección **Sesión** está en la barra lateral izquierda.")

def main():
    st.set_page_config(page_title="CPF – Sistema de Requerimientos", layout="wide")
    # Logo CPF: se renderiza dentro de la barra lateral (Sesión)

    u = None
    has_admin = any_admin_exists()

    with st.sidebar:
        _render_sidebar_logo()
        st.title("Sesión")

        if not has_admin:
            _admin_bootstrap_ui()
            _assistant_sidebar(role="anon")
        else:
            u = _get_user()
            if not u:
                c1, c2 = st.columns(2)
                with c1:
                    _login_ui()
                with c2:
                    _register_ui()
                _assistant_sidebar(role="anon")
            else:
                st.success(f"Usuario: {u['name']}")
                st.write(f"Empresa: {u['company']}")
                st.write(f"Rol: {u['role']}")

                # Backup automático al ingresar (solo admin)
                # _maybe_auto_backup("login")  # (deshabilitado: backup sólo al cerrar sesión)

                if is_super_admin(_uget(u, 'email', "")):
                    st.markdown("---")
                    st.subheader("Resguardo (solo Super Admin)")
                    _backup_download_ui()
                    st.markdown("---")

                    if st.session_state.get("_logout_confirm"):
                        st.warning("Se generó un backup al intentar cerrar sesión. Si querés, descargalo y luego confirmá.")
                        if st.button("✅ Confirmar cerrar sesión", use_container_width=True):
                            _logout()
                    else:
                        st.button("Cerrar sesión", on_click=_start_logout_with_backup, use_container_width=True)
                else:
                    st.button("Cerrar sesión", on_click=_logout, use_container_width=True)

                # Revisión 29: indicador de uso de disco (Admin) en la parte inferior de "Sesión".
                # Por defecto se muestra también a Super Admin para que el dueño del sistema pueda monitorear el disco.
                # Si querés ocultarlo para Super Admin, setear CPF_DISK_HIDE_SUPERADMIN=1 en Render.
                try:
                    if u.get("role") == "admin":
                        is_sa = is_super_admin(_uget(u, "email", ""))
                        hide_sa = os.getenv("CPF_DISK_HIDE_SUPERADMIN", "0") == "1"
                        if (not is_sa) or (not hide_sa):
                            st.markdown("---")
                            st.subheader("Almacenamiento")
                            _disk_usage_pie(os.getenv("CPF_DISK_MOUNT", "/var/data"))
                except Exception:
                    pass

                _assistant_sidebar(role=u["role"])

    # --------- Pantalla principal ---------
    if not has_admin:
        st.title("CPF – Sistema de Requerimientos (sin precios)")
        st.warning("Primera configuración: creá el **Super Admin inicial** desde la barra lateral (Sesión).")
        return

    if not u:
        _public_panel_home()
        return

    st.title("CPF – Sistema de Requerimientos (sin precios)")
    st.caption("Publicar OFERTAS/NECESIDADES, navegar, buscar y solicitar contacto. Negociación y precio: fuera del sistema.")

    with st.expander("📌 Alcances y reglas del sistema", expanded=False):
        st.markdown("""
        - **Sin precios:** el sistema no maneja precios ni rangos; la negociación queda fuera.
        - **Cámara/Institución obligatoria:** para registrarte debés elegir una cámara/institución existente.
        - **Teléfono obligatorio:** se utiliza también para recuperación de acceso.
        - **Registro sujeto a validación:** al registrarte quedás **pendiente** hasta que el **Asistente** de tu cámara o el **Super Admin** te habilite.
        - **Asistentes:** el personal administrativo (rol *assistant*) tiene un **panel único** y valida usuarios **solo** de su cámara.
        - **Adjuntos:** máximo **2** por publicación. **Adjunto 1 = imagen portada** (JPG/JPEG/PNG/GIF/WEBP).
        - **Seguridad:** se aceptan solo tipos permitidos; se bloquean ejecutables.
        - **Interesados:** al aceptar una solicitud, se muestran **contactos de ambos lados**.
        - **Recuperación de contraseña:** desde **Olvidé mi contraseña** se envía una **clave provisoria por email** para definir una nueva clave.
        - **Backups:** el Super Admin puede crear y restaurar copias de seguridad.
        """)

    # v49: los asistentes tienen un panel único y acotado por cámara.
    if str(u.get("role") or "user").strip().lower() == "assistant":
        _assistant_approval_panel(u)
        return


    role = u["role"] if u else "anon"
    is_sa = bool(u and is_super_admin(_uget(u, 'email', '')))
    tab_names = ["Navegar", "Publicar", "Bandeja", "Panel", "Interesados", "Asistente IA"]
    if is_sa:
        tab_names.append("Dar de alta")
        tab_names.append("Validar usuarios")
    t = st.tabs(tab_names)


    with t[0]:
        st.header("Requisitos del navegador")

        chambers = svc.list_chambers()
        chamber_options = ["(Todas)"] + [c["name"] for c in chambers]
        chamber_sel = st.selectbox("Cámara", chamber_options)
        chamber_id = None
        if chamber_sel != "(Todas)":
            for c in chambers:
                if c["name"] == chamber_sel:
                    chamber_id = c["id"]
                    break

        q = st.text_input("Buscar (producto/palabra clave/empresa/persona/tags)")
        tipo = st.selectbox("Tipo", ["(Todos)", "need", "offer"],
                            format_func=lambda x: {"(Todos)": "(Todos)", "need": "Necesidad", "offer": "Oferta"}.get(x, x))
        is_sa = bool(u and is_super_admin(_uget(u, 'email', '')))
        status_options = ["open", "closed"] if not is_sa else ["(Todos)", "open", "closed", "annulled"]
        status = st.selectbox(
            "Estado",
            status_options,
            format_func=lambda x: {"(Todos)": "(Todos)", "open": "abierto", "closed": "cerrado", "annulled": "anulado"}.get(x, x),
        )
        status_param = "" if status == "(Todos)" else status

        reqs = svc.search_requirements(q=q, type_=tipo, status=status_param, chamber_id=chamber_id)

        
        st.subheader(f"Resultados ({len(reqs)})")
        for r in reqs:
            status_r = (r.get("status") or "open").lower()
            is_ann = status_r == "annulled"
            kind = "NECESIDAD" if r.get("type") == "need" else "OFERTA"
            badge = " 🟥 ANULADO" if is_ann else ""
            color = "red" if is_ann else "black"

            st.markdown(
                f"<div style='color:{color}; font-weight:600'>#{r['id']} · {kind} · {r['title']}{badge}</div>",
                unsafe_allow_html=True,
            )

            with st.expander("Ver detalles", expanded=False):
                if is_ann:
                    st.markdown("<div style='color:red; font-weight:700'>REQUERIMIENTO ANULADO POR MODERACIÓN</div>", unsafe_allow_html=True)

                st.write(f"**Empresa:** {r['company']}")
                st.write(f"**Cámara:** {r.get('chamber_name') or '(Sin cámara)'}")
                if r.get("category"):
                    st.write(f"**Categoría:** {r['category']}")
                st.write(f"**Urgencia:** {r.get('urgency','Media')}")
                if r.get("tags"):
                    st.write(f"**Tags:** {r['tags']}")
                cover = svc.get_cover_image_bytes(r["id"])
                if cover and cover.get("bytes"):
                    st.image(cover["bytes"], width=320)

                st.write(r["description"])

                atts = svc.list_attachments(r["id"])
                if atts:
                    if len(atts) > MAX_ATTACHMENTS:
                        st.caption(f"Se muestran los primeros {MAX_ATTACHMENTS} adjuntos (hay {len(atts)}).")
                    st.write("**Adjuntos:**")
                    for a in atts[:MAX_ATTACHMENTS]:
                        data = svc.read_attachment_bytes(a["id"])
                        size = int(a.get("size") or 0)
                        size_kb = f"{max(1, size // 1024)} KB" if size else "?"
                        mime = "application/pdf" if str(a.get("filename", "")).lower().endswith(".pdf") else "application/octet-stream"
                        if data:
                            st.download_button(
                                label=f"⬇️ Descargar {a['filename']} ({size_kb})",
                                data=data,
                                file_name=a["filename"],
                                mime=mime,
                                key=f"dl_att_{a['id']}"
                            )
                        else:
                            st.write(f"- {a['filename']} ({size_kb}) — archivo no disponible")

                if u and int(u["id"]) != int(r["user_id"]):
                    if status_r != "open":
                        st.caption("Contacto deshabilitado: el requerimiento no está abierto.")
                    else:
                        if st.button("Solicitar contacto", key=f"contact_{r['id']}"):
                            svc.create_contact_request(from_user_id=u["id"], to_user_id=r["user_id"], requirement_id=r["id"])
                            try:
                                # Notificaciones por mail (si está configurado SMTP)
                                req = svc.get_requirement(int(r["id"]))
                                cdb = db_conn()
                                owner = cdb.execute("SELECT email, name FROM users WHERE id=?", (int(req["user_id"]),)).fetchone()
                                cdb.close()
                                mailer.notify_interest_owner(
                                    owner_email=(owner["email"] if owner else ""),
                                    owner_name=(owner["name"] if owner else ""),
                                    kind=(req.get("type") or ""),
                                    title=(req.get("title") or ""),
                                    company=(req.get("company") or ""),
                                )
                                mailer.notify_interest_sender(
                                    sender_email=(u.get("email") or ""),
                                    sender_name=(u.get("name") or ""),
                                    kind=(req.get("type") or ""),
                                    title=(req.get("title") or ""),
                                    company=(req.get("company") or ""),
                                )
                            except Exception:
                                try:
                                    cdb.close()
                                except Exception:
                                    pass
                            st.success("Solicitud enviada.")

    with t[1]:
        st.header("Publicar un requerimiento")

        # NOTA: st.file_uploader dentro de st.form puede fallar en algunos casos.
        # Por eso lo dejamos fuera del form.
        st.subheader("Adjuntos (opcional)")
        files = st.file_uploader(
            "Adjuntar archivos — OBLIGATORIO: el adjunto 1 debe ser una imagen (JPG/JPEG/PNG/GIF/WEBP) como portada; luego PDFs/Word/Excel",
            type=["jpg", "jpeg", "png", "gif", "webp", "pdf", "doc", "docx", "xls", "xlsx"],
            accept_multiple_files=True,
            key="publish_files",
            help="Por seguridad solo se aceptan imágenes (JPG/JPEG/PNG/GIF/WEBP) y documentos (PDF/Word/Excel). Si el archivo es grande y no sube, probá con uno más liviano. Máximo de adjuntos por publicación: 2 (se controla automáticamente).",
        )
        if files:
            st.caption("Seleccionados: " + ", ".join([f.name for f in files]))
            if len(files) > MAX_ATTACHMENTS:
                st.warning(f"Seleccionaste {len(files)} adjuntos. El máximo permitido es {MAX_ATTACHMENTS}. Eliminá algunos antes de publicar.")

        chambers = svc.list_chambers()
        chamber_options = ["(Sin cámara)"] + [c["name"] for c in chambers]

        with st.form("publish_form"):
            type_ = st.selectbox("Tipo", ["need", "offer"],
                                 format_func=lambda x: {"need": "Necesidad", "offer": "Oferta"}[x])
            title = st.text_input("Título")
            desc = st.text_area("Descripción", height=160)

            category = st.selectbox("Categoría (obligatoria)", ["(Sin categoría)"] + CATEGORIES)
            urgency = st.selectbox("Urgencia", URGENCY, index=1)
            tags = st.text_input("Tags (opcional, separados por coma)")

            chamber_sel = st.selectbox("Cámara (opcional)", chamber_options)
            chamber_id = None
            if chamber_sel != "(Sin cámara)":
                for c in chambers:
                    if c["name"] == chamber_sel:
                        chamber_id = c["id"]
                        break

            location = st.text_input("Ubicación (obligatoria)")

            ok = st.form_submit_button("Publicar")

        if ok:
            errors = []
            if not title.strip():
                errors.append("• Título (obligatorio).")
            if not desc.strip():
                errors.append("• Descripción (obligatoria).")
            if REQUIRE_CATEGORY and category == "(Sin categoría)":
                errors.append("• Categoría (obligatoria). Elegí una categoría.")
            if REQUIRE_LOCATION and not location.strip():
                errors.append("• Ubicación (obligatoria).")
            if files and len(files) > MAX_ATTACHMENTS:
                errors.append(f"• Máximo {MAX_ATTACHMENTS} adjuntos por publicación.")
            if REQUIRE_COVER_IMAGE:
                if not files:
                    errors.append("• Adjuntá una imagen como primer archivo (portada).")
                else:
                    first_ext = (files[0].name.split(".")[-1] if getattr(files[0], "name", None) else "").lower()
                    if first_ext not in IMAGE_EXTS:
                        errors.append("• El adjunto 1 debe ser una imagen (JPG/JPEG/PNG/GIF/WEBP).")

            if errors:
                st.error("Faltan datos o hay problemas:\n" + "\n".join(errors))
            else:
                rev = review_requirement(title, desc)
                if not rev.get("ok", True):
                    st.error(rev.get("reason", "El texto no pasó la moderación."))
                    if rev.get("hits"):
                        st.write("Palabras detectadas:", ", ".join(rev["hits"]))
                else:
                    final_title = rev.get("suggested_title", title).strip()
                    final_desc = rev.get("suggested_description", desc).strip()
                    final_category = None if category == "(Sin categoría)" else category

                    req_id = svc.create_requirement(
                        type_=type_,
                        title=final_title,
                        description=final_desc,
                        user_id=u["id"],
                        company=u["company"],
                        chamber_id=chamber_id,
                        location=location.strip() or None,
                        category=final_category,
                        urgency=urgency,
                        tags=tags,
                    )

                    if files:
                        for f in files:
                            try:
                                svc.save_attachment(
                                    requirement_id=req_id,
                                    uploaded_by_user_id=u["id"],
                                    filename=f.name,
                                    content=f.getvalue(),
                                    mime=getattr(f, "type", None),
                                )
                            except Exception as e:
                                st.warning(f"No se pudo guardar {f.name}: {e}")

                    st.success(f"Requerimiento publicado con ID #{req_id}.")

    with t[2]:
        st.header("Bandeja")

        st.subheader("Solicitudes de contacto recibidas")
        inbox = svc.list_inbox(u["id"], status="pending")
        if not inbox:
            st.write("No tenés solicitudes pendientes.")
        else:
            for it in inbox:
                with st.expander(f"Solicitud #{it['id']} — {it['from_name']} por #{it['requirement_id']} · {it['title']}"):
                    st.write(f"**Contacto:** {it['from_name']} · {it['from_email']} · {it.get('from_phone') or ''}")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Aceptar", key=f"acc_{it['id']}"):
                            svc.respond_contact_request(it["id"], "accepted")
                            try:
                                cdb = db_conn()
                                cr = cdb.execute("SELECT from_user_id, requirement_id FROM contact_requests WHERE id=?", (int(it["id"]),)).fetchone()
                                if cr:
                                    req = svc.get_requirement(int(cr["requirement_id"]))
                                    owner = cdb.execute("SELECT email, name FROM users WHERE id=?", (int(req["user_id"]),)).fetchone()
                                    sender = cdb.execute("SELECT email, name FROM users WHERE id=?", (int(cr["from_user_id"]),)).fetchone()
                                    mailer.notify_accept_both(
                                        owner_email=(owner["email"] if owner else ""),
                                        owner_name=(owner["name"] if owner else ""),
                                        sender_email=(sender["email"] if sender else ""),
                                        sender_name=(sender["name"] if sender else ""),
                                        kind=(req.get("type") or ""),
                                        title=(req.get("title") or ""),
                                        company=(req.get("company") or ""),
                                    )
                                cdb.close()
                            except Exception:
                                try:
                                    cdb.close()
                                except Exception:
                                    pass
                            st.success("Aceptada.")
                            st.rerun()
                    with c2:
                        if st.button("Rechazar", key=f"dec_{it['id']}"):
                            svc.respond_contact_request(it["id"], "declined")
                            st.info("Rechazada.")
                            st.rerun()

        st.divider()
        
        st.subheader("Mis publicaciones")
        st.caption("Tip: tocá **Editar** para abrir la ficha y corregir tu publicación (incluye adjuntos).")
        mine = svc.list_user_requirements(u["id"])
        if not mine:
            st.write("Todavía no publicaste requerimientos.")
        else:
            for r in mine:
                status_r = (r.get("status") or "open").lower()
                is_ann = status_r == "annulled"
                kind = "NECESIDAD" if r.get("type") == "need" else "OFERTA"
                color = "red" if is_ann else "black"
                badge = " 🟥 ANULADO" if is_ann else ""

                open_key = f"edit_open_{r['id']}"
                cols = st.columns([8, 2])
                with cols[0]:
                    st.markdown(
                        f"<div style='color:{color}; font-weight:600'>#{r['id']} · {kind} · {r['title']}{badge}</div>",
                        unsafe_allow_html=True,
                    )
                with cols[1]:
                    if st.button("✏️ Editar", key=f"btn_edit_{r['id']}"):
                        st.session_state[open_key] = not st.session_state.get(open_key, False)

                with st.expander("Ficha de publicación", expanded=st.session_state.get(open_key, False)):
                    if is_ann:
                        st.markdown("<div style='color:red; font-weight:700'>REQUERIMIENTO ANULADO POR MODERACIÓN</div>", unsafe_allow_html=True)

                    # Si está anulado y NO sos Super Admin: solo lectura (no puede re-abrirlo)
                    if is_ann and not is_sa:
                        st.write(r.get("description") or "")
                        if r.get("category"):
                            st.write(f"**Categoría:** {r.get('category')}")
                        st.write(f"**Urgencia:** {r.get('urgency','media')}")
                        if r.get("tags"):
                            st.write(f"**Tags:** {r.get('tags')}")
                        st.caption("Este requerimiento fue anulado por moderación y no puede editarse.")
                        continue

                    cover = svc.get_cover_image_bytes(r["id"])
                    if cover and cover.get("bytes"):
                        st.image(cover["bytes"], width=320)

                    st.markdown("#### Adjuntos")
                    atts = svc.list_attachments(r["id"])
                    if atts and len(atts) > MAX_ATTACHMENTS:
                        st.caption(f"Se muestran los primeros {MAX_ATTACHMENTS} adjuntos (hay {len(atts)}).")
                    if not atts:
                        st.caption("Sin adjuntos.")
                    else:
                        for a in atts:
                            fname = a.get("filename") or "archivo"
                            size = int(a.get("size") or 0)
                            size_kb = f"{max(size/1024.0, 0.1):.0f} KB" if size else "?"
                            data = svc.read_attachment_bytes(a["id"])
                            mime = "application/pdf" if str(fname).lower().endswith(".pdf") else "application/octet-stream"

                            c_dl, c_del = st.columns([4, 1])
                            with c_dl:
                                if data:
                                    st.download_button(
                                        label=f"⬇️ Descargar {fname} ({size_kb})",
                                        data=data,
                                        file_name=fname,
                                        mime=mime,
                                        key=f"dl_att_my_{a['id']}",
                                    )
                                else:
                                    st.write(f"- {fname} ({size_kb}) — archivo no disponible")
                            with c_del:
                                if st.button("🗑️", key=f"del_att_btn_{a['id']}"):
                                    ok = svc.delete_attachment(a["id"], u["id"], is_sa)
                                    if ok:
                                        st.success("Adjunto eliminado.")
                                        st.rerun()
                                    else:
                                        st.error("No tenés permisos para eliminar este adjunto.")

                    new_files = st.file_uploader(
                        "Agregar adjuntos (opcional) — máximo 2 en total por publicación",
                        type=["jpg", "jpeg", "png", "gif", "webp", "pdf", "doc", "docx", "xls", "xlsx"],
                        accept_multiple_files=True,
                        key=f"edit_files_{r['id']}",
                    )
                    if new_files:
                        st.caption("Seleccionados: " + ", ".join([f.name for f in new_files]))
                        if len(new_files) > MAX_ATTACHMENTS:
                            st.warning(f"Seleccionaste {len(new_files)} adjuntos. El máximo permitido es {MAX_ATTACHMENTS}.")
                        # Control adicional: total de adjuntos permitidos por publicación
                        current_atts = svc.list_attachments(r["id"])
                        remaining = max(0, MAX_ATTACHMENTS - (len(current_atts) if current_atts else 0))
                        if remaining == 0:
                            st.error(f"Esta publicación ya tiene {MAX_ATTACHMENTS} adjuntos. Eliminá alguno para subir uno nuevo.")
                        else:
                            st.caption(f"Podés subir hasta {remaining} adjunto(s) más.")
                            if st.button("📎 Subir adjuntos", key=f"upload_att_{r['id']}"):
                                try:
                                    svc.add_attachments(r["id"], new_files, u["id"])
                                    st.success("Adjuntos subidos.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"No se pudieron subir los adjuntos: {e}")

                    with st.form(f"edit_{r['id']}"):
                        title2 = st.text_input("Título", value=r["title"])
                        desc2 = st.text_area("Descripción", value=r["description"], height=120)
                        cat2 = st.selectbox(
                            "Categoría",
                            ["(Sin categoría)"] + CATEGORIES,
                            index=(["(Sin categoría)"] + CATEGORIES).index(r.get("category") or "(Sin categoría)"),
                        )
                        urg_val = r.get("urgency") or "media"
                        urg2 = st.selectbox(
                            "Urgencia",
                            URGENCY,
                            index=URGENCY.index(urg_val) if urg_val in URGENCY else 1,
                        )
                        tags2 = st.text_input("Tags", value=r.get("tags") or "")

                        status_options2 = ["open", "closed"] + (["annulled"] if is_sa else [])
                        cur_status = r.get("status") if r.get("status") in status_options2 else "open"
                        status2 = st.selectbox(
                            "Estado",
                            status_options2,
                            index=status_options2.index(cur_status),
                            format_func=lambda x: {"open": "abierto", "closed": "cerrado", "annulled": "anulado"}.get(x, x),
                        )

                        save = st.form_submit_button("Guardar cambios")
                        if save:
                            rev = review_requirement(title2, desc2)
                            if not rev.get("ok", True):
                                st.error(rev.get("reason", "El texto no pasó la moderación."))
                            else:
                                svc.update_requirement(
                                    r["id"],
                                    title=rev.get("suggested_title", title2),
                                    description=rev.get("suggested_description", desc2),
                                    category=None if cat2 == "(Sin categoría)" else cat2,
                                    urgency=urg2,
                                    tags=tags2,
                                    status=status2,
                                )
                                st.success("Actualizado.")
                                st.rerun()

    with t[3]:
        st.header("Panel")
        m = svc.admin_metrics()

        # Mantener consistencia con la Vista Pública (misma lógica y mismos 6 indicadores)
        r1 = st.columns(2)
        r1[0].metric("Publicaciones activas", int(m.get("open_requirements", 0)))
        r1[1].metric("Usuarios registrados", int(m.get("users", 0)))

        r2 = st.columns(2)
        r2[0].metric("Solicitudes pendientes", int(m.get("contacts_pending", 0)))
        r2[1].metric("Contactos aprobados", int(m.get("contacts_accepted", 0)))

        r3 = st.columns(2)
        r3[0].metric("Cámaras", int(m.get("chambers", 0)))
        r3[1].metric("Solicitudes rechazadas", int(m.get("contacts_declined", 0)))

        st.subheader("Requerimientos por cámara")
        if m["requirements_by_chamber"]:
            st.dataframe(m["requirements_by_chamber"], use_container_width=True)



        # Usuarios (solo Super Admin): permite auditar registros y detectar cuentas inesperadas
        if u and is_super_admin(_uget(u, "email", "")):
            st.divider()
            st.subheader("Usuarios registrados (solo Super Admin)")
            q_user = st.text_input("Buscar usuario (email, nombre o empresa)", key="su_user_search")
            users_list = svc.list_users(q_user or None)
            st.caption(f"Total: {len(users_list)} usuario(s).")
            if users_list:
                # Edición directa (tipo Excel) para pequeñas correcciones administrativas
                df_full_u = pd.DataFrame(users_list)

                # Opciones de cámara para edición rápida
                chambers_all = svc.list_chambers()
                chamber_label_none = "Sin cámara"
                chamber_options = [chamber_label_none] + [c.get("name") for c in chambers_all if c.get("name")]
                chamber_name_to_id = {c.get("name"): int(c.get("id")) for c in chambers_all if c.get("name") and c.get("id") is not None}
                cols = [
                    "id",
                    "email",
                    "name",
                    "company",
                    "chamber",
                    "phone",
                    "role",
                    "is_active",
                    "is_approved",
                    "approved_at",
                ]
                df_u = df_full_u.copy()
                # Normalizar visualización de cámara
                if "chamber_name" in df_u.columns:
                    df_u["chamber"] = df_u["chamber_name"].fillna(chamber_label_none)
                elif "chamber" not in df_u.columns:
                    df_u["chamber"] = chamber_label_none

                df_u = df_u[[c for c in cols if c in df_u.columns]].copy()
                if "is_active" in df_u.columns:
                    df_u["is_active"] = df_u["is_active"].fillna(0).astype(int).astype(bool)
                if "is_approved" in df_u.columns:
                    df_u["is_approved"] = df_u["is_approved"].fillna(0).astype(int).astype(bool)

                edited_u = st.data_editor(
                    df_u,
                    key="su_users_editor",
                    use_container_width=True,
                    disabled=["id"],
                    column_config={
                        "chamber": st.column_config.SelectboxColumn(
                            "chamber",
                            options=chamber_options,
                            required=True,
                            help="Cámara a la que está asociado el usuario (solo Super Admin).",
                        ),
                        "role": st.column_config.SelectboxColumn(
                            "role",
                            options=["user", "admin", "assistant"],
                            required=True,
                        ),
                        "is_active": st.column_config.CheckboxColumn("is_active"),
                        "is_approved": st.column_config.CheckboxColumn("is_approved"),
                        "approved_at": st.column_config.TextColumn(
                            "approved_at",
                            help="Formato ISO 8601 (ej: 2026-02-13T18:20:00Z). Vacío = NULL.",
                        ),
                    },
                )

                if st.button("💾 Guardar cambios (usuarios)", key="su_users_save"):
                    def _norm_s(v):
                        try:
                            if pd.isna(v):
                                return None
                        except Exception:
                            pass
                        if v is None:
                            return None
                        s = str(v).strip()
                        return s if s != "" else None

                    orig = df_u.set_index("id")
                    new = edited_u.set_index("id")
                    # Mapa id_usuario -> chamber_id (normalizado)
                    orig_chamber_id = {}
                    try:
                        if "chamber_id" in df_full_u.columns and "id" in df_full_u.columns:
                            for _row in df_full_u[["id", "chamber_id"]].itertuples(index=False):
                                uid0 = int(getattr(_row, "id"))
                                v = getattr(_row, "chamber_id")
                                try:
                                    if pd.isna(v):
                                        v = None
                                except Exception:
                                    pass
                                orig_chamber_id[uid0] = (int(v) if v is not None else None)
                    except Exception:
                        orig_chamber_id = {}
                    changed = 0
                    errors = []

                    for uid in new.index:
                        try:
                            o = orig.loc[uid]
                        except Exception:
                            continue
                        r = new.loc[uid]

                        # Normalizaciones
                        email_n = (_norm_s(r.get("email")) or "").lower()
                        name_n = _norm_s(r.get("name"))
                        company_n = _norm_s(r.get("company"))
                        chamber_n = _norm_s(r.get("chamber"))
                        phone_n = _norm_s(r.get("phone"))
                        role_n = (_norm_s(r.get("role")) or "user").lower()
                        is_active_n = 1 if bool(r.get("is_active")) else 0
                        is_approved_n = 1 if bool(r.get("is_approved")) else 0
                        approved_at_n = _norm_s(r.get("approved_at"))

                        # Cámara (nombre -> id)
                        if not chamber_n or chamber_n == chamber_label_none:
                            chamber_id_n = None
                        else:
                            if chamber_n not in chamber_name_to_id:
                                errors.append(f"Usuario #{uid}: cámara inválida ({chamber_n})")
                                continue
                            chamber_id_n = int(chamber_name_to_id[chamber_n])

                        # Reglas: coherencia aprobación/fecha
                        if is_approved_n == 0:
                            approved_at_n = None
                        elif is_approved_n == 1 and not approved_at_n:
                            approved_at_n = now_iso()

                        # Validaciones mínimas
                        if not email_n or "@" not in email_n:
                            errors.append(f"Usuario #{uid}: email inválido")
                            continue
                        if not name_n:
                            errors.append(f"Usuario #{uid}: nombre vacío")
                            continue
                        if role_n not in {"user", "admin", "assistant"}:
                            errors.append(f"Usuario #{uid}: role inválido ({role_n})")
                            continue

                        # Detectar cambios reales (comparación normalizada)
                        def _same(a, b):
                            return (_norm_s(a) or "") == (_norm_s(b) or "")

                        fields = {}
                        if not _same(r.get("email"), o.get("email")):
                            fields["email"] = email_n
                        if not _same(r.get("name"), o.get("name")):
                            fields["name"] = name_n
                        if not _same(r.get("company"), o.get("company")):
                            fields["company"] = company_n
                        # chamber_id
                        if orig_chamber_id.get(int(uid)) != chamber_id_n:
                            fields["chamber_id"] = chamber_id_n
                        if not _same(r.get("phone"), o.get("phone")):
                            fields["phone"] = phone_n
                        if not _same(r.get("role"), o.get("role")):
                            fields["role"] = role_n
                        if int(bool(o.get("is_active"))) != int(bool(r.get("is_active"))):
                            fields["is_active"] = is_active_n
                        if int(bool(o.get("is_approved"))) != int(bool(r.get("is_approved"))):
                            fields["is_approved"] = is_approved_n
                        # approved_at: se compara siempre (por reglas puede haber cambiado)
                        if (_norm_s(o.get("approved_at")) or "") != (_norm_s(approved_at_n) or ""):
                            fields["approved_at"] = approved_at_n

                        if not fields:
                            continue

                        try:
                            svc.update_user_superadmin(int(uid), **fields)
                            changed += 1
                        except Exception as e:
                            errors.append(f"Usuario #{uid}: {e}")

                    if errors:
                        st.error("Se aplicaron cambios parciales. Detalles:\n- " + "\n- ".join(errors))
                    if changed:
                        st.success(f"Cambios guardados en {changed} usuario(s).")
                        st.rerun()
                    else:
                        st.info("No se detectaron cambios para guardar.")
            else:
                st.info("No hay usuarios que coincidan con la búsqueda.")

            st.divider()
            st.subheader("Administración de Cámaras (solo Super Admin)")
            chambers = svc.list_chambers()
            if chambers:
                df_c = pd.DataFrame(chambers)
                df_c = df_c[[c for c in ["id", "name", "province", "city"] if c in df_c.columns]].copy()

                edited_c = st.data_editor(
                    df_c,
                    key="su_chambers_editor",
                    use_container_width=True,
                    disabled=["id"],
                    column_config={
                        "name": st.column_config.TextColumn("name", required=True),
                        "province": st.column_config.TextColumn("province"),
                        "city": st.column_config.TextColumn("city"),
                    },
                )

                if st.button("💾 Guardar cambios (cámaras)", key="su_chambers_save"):
                    def _norm_s(v):
                        try:
                            if pd.isna(v):
                                return None
                        except Exception:
                            pass
                        if v is None:
                            return None
                        s = str(v).strip()
                        return s if s != "" else None

                    origc = df_c.set_index("id")
                    newc = edited_c.set_index("id")
                    changed_c = 0
                    errors_c = []
                    for cid in newc.index:
                        try:
                            o = origc.loc[cid]
                        except Exception:
                            continue
                        r = newc.loc[cid]

                        name_n = _norm_s(r.get("name"))
                        prov_n = _norm_s(r.get("province"))
                        city_n = _norm_s(r.get("city"))
                        if not name_n:
                            errors_c.append(f"Cámara #{cid}: nombre vacío")
                            continue

                        fields = {}
                        if (_norm_s(o.get("name")) or "") != (name_n or ""):
                            fields["name"] = name_n
                        if (_norm_s(o.get("province")) or "") != (_norm_s(prov_n) or ""):
                            fields["province"] = prov_n
                        if (_norm_s(o.get("city")) or "") != (_norm_s(city_n) or ""):
                            fields["city"] = city_n
                        if not fields:
                            continue
                        try:
                            svc.update_chamber_superadmin(int(cid), **fields)
                            changed_c += 1
                        except Exception as e:
                            errors_c.append(f"Cámara #{cid}: {e}")

                    if errors_c:
                        st.error("Se aplicaron cambios parciales. Detalles:\n- " + "\n- ".join(errors_c))
                    if changed_c:
                        st.success(f"Cambios guardados en {changed_c} cámara(s).")
                        st.rerun()
                    else:
                        st.info("No se detectaron cambios para guardar.")
            else:
                st.info("Aún no hay cámaras cargadas.")
            with st.form("add_chamber"):
                nm = st.text_input("Nombre cámara")
                loc = st.text_input("Ciudad/Provincia (opcional)")
                ok2 = st.form_submit_button("Crear cámara")
                if ok2:
                    if svc.create_chamber(nm.strip(), loc.strip() or None):
                        st.success("Cámara creada.")
                        st.rerun()
                    else:
                        st.error("No se pudo crear (¿ya existe?).")

    with t[4]:
        st.header("Interesados")
        st.caption(
            "Historial de solicitudes de contacto: las que **recibís** por tus publicaciones y las que **enviás** a otros."
        )

        subt = st.tabs(["📥 Recibidas", "📤 Enviadas"])

        def _fmt_contact(name: str, email: str, phone: str, company: str = None) -> str:
            bits = []
            if name:
                bits.append(name)
            if company:
                bits.append(company)
            if email:
                bits.append(email)
            if phone:
                bits.append(phone)
            return " · ".join(bits) if bits else "-"

        # -------------------- Recibidas (inbox) --------------------
        with subt[0]:
            st.subheader("📥 Recibidas por mis publicaciones")
            st.caption("Solicitudes de contacto recibidas por tus publicaciones (queda el historial aunque ya las aceptes/rechaces).")

            def _show_inbox(item):
                kind = "OFERTA" if item.get("type") == "offer" else "NECESIDAD"
                title = item.get("title") or "(sin título)"
                status = (item.get("status") or "").strip().lower() or "pending"

                st.write(f"**Solicitud #{item['id']} — {kind} #{item['requirement_id']} · {title}**")
                st.write(f"Estado: **{status}**")
                if item.get("created_at"):
                    st.write(f"Creada: {item.get('created_at')}")
                if item.get("responded_at"):
                    st.write(f"Respondida: {item.get('responded_at')}")

                # Acciones (solo si está pendiente)
                if status == "pending":
                    c1, c2, _ = st.columns([1, 1, 6])
                    with c1:
                        if st.button("✅ Aceptar", key=f"acc_inbox_{item['id']}"):
                            svc.respond_contact_request(int(item["id"]), "accepted")
                            try:
                                mailer.notify_accept_both(
                                    owner_email=(item.get("to_email") or ""),
                                    owner_name=(item.get("to_name") or ""),
                                    sender_email=(item.get("from_email") or ""),
                                    sender_name=(item.get("from_name") or ""),
                                    kind=kind,
                                    title=title,
                                    company=(item.get("company") or ""),
                                )
                            except Exception:
                                pass
                            st.success("Solicitud aceptada.")
                            st.rerun()
                    with c2:
                        if st.button("⛔ Rechazar", key=f"dec_inbox_{item['id']}"):
                            svc.respond_contact_request(int(item["id"]), "declined")
                            st.info("Solicitud rechazada.")
                            st.rerun()

                st.write("")
                st.write("**Contactos:**")

                # Regla: no mostrar email/teléfono hasta que se acepte
                if status != "accepted":
                    st.write("- Interesado: " + (item.get("from_name") or "(sin nombre)") + " · " + (item.get("from_company") or "(sin empresa)"))
                    st.caption("Los datos de contacto (email/teléfono) se habilitan únicamente cuando aceptás la solicitud.")
                else:
                    def _fmt_full(name: str, company: str, email: str, phone: str) -> str:
                        parts = []
                        if name: parts.append(name)
                        if company: parts.append(company)
                        if email: parts.append(email)
                        if phone: parts.append(phone)
                        return " · ".join(parts) if parts else "-"

                    st.write("- Interesado: " + _fmt_full(item.get("from_name",""), item.get("from_company",""), item.get("from_email",""), item.get("from_phone","")))
                    st.write("- Tu contacto: " + _fmt_full(item.get("to_name",""), item.get("to_company",""), item.get("to_email",""), item.get("to_phone","")))

            accepted = svc.list_inbox(u["id"], status="accepted")
            pending = svc.list_inbox(u["id"], status="pending")
            declined = svc.list_inbox(u["id"], status="declined")

            st.markdown("---")
            st.markdown("## ✅ Aceptadas")
            if not accepted:
                st.write("No tenés solicitudes aceptadas.")
            else:
                for it in accepted:
                    with st.container(border=True):
                        _show_inbox(it)

            st.markdown("---")
            st.markdown("## ⏳ Pendientes")
            if not pending:
                st.write("No tenés solicitudes pendientes.")
            else:
                for it in pending:
                    with st.container(border=True):
                        _show_inbox(it)

            st.markdown("---")
            st.markdown("## ⛔ Rechazadas")
            if not declined:
                st.write("No tenés solicitudes rechazadas.")
            else:
                for it in declined:
                    with st.container(border=True):
                        _show_inbox(it)

        # -------------------- Enviadas (outbox) --------------------
        with subt[1]:
            st.subheader("📤 Enviadas por mí")
            st.caption(
                "Solicitudes de contacto que **vos** enviaste a otras publicaciones. "
                "El contacto de la otra parte se muestra cuando la solicitud fue **aceptada**."
            )

            def _show_outbox(item):
                kind = "OFERTA" if item.get("type") == "offer" else "NECESIDAD"
                title = item.get("title") or "(sin título)"
                st.write(f"**Solicitud #{item['id']} — a {item.get('to_name','-')} · {kind} #{item['requirement_id']} · {title}**")
                st.write(f"Estado: **{item.get('status')}**")
                if item.get("created_at"):
                    st.write(f"Creada: {item.get('created_at')}")
                if item.get("responded_at"):
                    st.write(f"Respondida: {item.get('responded_at')}")

                st.write("")
                st.write("**Contactos:**")
                # Tu contacto siempre
                st.write(
                    f"- **Tu contacto:** {_fmt_contact(item.get('from_name'), item.get('from_email'), item.get('from_phone'), item.get('from_company'))}"
                )

                # Contacto del dueño: solo si aceptada
                if str(item.get("status")) == "accepted":
                    st.write(
                        f"- **Dueño de la publicación:** {_fmt_contact(item.get('to_name'), item.get('to_email'), item.get('to_phone'), item.get('to_company'))}"
                    )
                else:
                    st.write(
                        f"- **Dueño de la publicación:** {item.get('to_name','-')} · {item.get('to_company') or '-'} · (contacto disponible al aceptar)"
                    )

            accepted = svc.list_outbox(u["id"], status="accepted")
            pending = svc.list_outbox(u["id"], status="pending")
            declined = svc.list_outbox(u["id"], status="declined")

            st.markdown("---")
            st.markdown("## ✅ Aceptadas")
            if not accepted:
                st.write("No tenés solicitudes aceptadas.")
            else:
                for it in accepted:
                    with st.container(border=True):
                        _show_outbox(it)

            st.markdown("---")
            st.markdown("## ⏳ Pendientes")
            if not pending:
                st.write("No tenés solicitudes pendientes.")
            else:
                for it in pending:
                    with st.container(border=True):
                        _show_outbox(it)

            st.markdown("---")
            st.markdown("## ⛔ Rechazadas")
            if not declined:
                st.write("No tenés solicitudes rechazadas.")
            else:
                for it in declined:
                    with st.container(border=True):
                        _show_outbox(it)

    with t[5]:
        st.header("Asistente IA")
        st.caption("Chat de ayuda sobre el funcionamiento y consultas (modo local/IA).")

        if "chat" not in st.session_state:
            st.session_state["chat"] = []

        for msg in st.session_state["chat"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        q = st.chat_input("Escribí tu consulta…")
        if q:
            st.session_state["chat"].append({"role": "user", "content": q})
            with st.chat_message("user"):
                st.markdown(q)

            out = assistant_answer(q, role=role)
            ans = out.get("answer", "")
            with st.chat_message("assistant"):
                st.markdown(ans)
                if out.get("table") is not None:
                    st.dataframe(out["table"], use_container_width=True)

            st.session_state["chat"].append({"role": "assistant", "content": ans})


    # Tab extra: administración (solo Super Admin)
    if is_sa:
        admin_tab_idx = tab_names.index("Dar de alta")
        validate_tab_idx = tab_names.index("Validar usuarios")

        with t[admin_tab_idx]:
            st.header("Dar de alta (solo Super Admin)")

            st.subheader("Super Administradores")
            current_sas = get_super_admin_emails()
            if current_sas:
                st.write("**Super Admin(s) actuales:** " + ", ".join(current_sas))
            else:
                st.warning("No hay Super Admins configurados. (Esto no debería ocurrir.)")

            import secrets

            with st.form("sa_add_form"):
                st.caption("Otorgar o quitar permisos de Super Admin se basa en el **email**. No requiere re-login: con el próximo refresh/rerun ya aplica.")
                email_sa = st.text_input("Email del usuario", placeholder="usuario@empresa.com")
                name_sa = st.text_input("Nombre y Apellido (opcional)", placeholder="Nombre Apellido")
                create_if_missing = st.checkbox("Si el usuario no existe, crearlo con contraseña temporal", value=True)
                ok_sa = st.form_submit_button("✅ Otorgar permisos de Super Admin")

                if ok_sa:
                    em = (email_sa or "").strip().lower()
                    nm = (name_sa or "").strip()
                    if not em:
                        st.error("Ingresá un email.")
                    else:
                        temp_pass = None
                        urow = get_user_by_email(em)
                        if urow:
                            # Actualiza nombre si se proporcionó
                            if nm and (urow["name"] or "").strip() != nm:
                                c = db_conn()
                                c.execute("UPDATE users SET name=? WHERE email=?", (nm, em))
                                c.commit()
                                c.close()
                        else:
                            if not create_if_missing:
                                st.error("El usuario no existe. Activá la opción de crearlo acá o pedile que se registre.")
                            else:
                                temp_pass = secrets.token_urlsafe(10)
                                create_user(
                                    em,
                                    temp_pass,
                                    nm or em,
                                    company="",
                                    phone=None,
                                    role="user",
                                    chamber_id=None,
                                )

                        # Otorga permiso SA (idempotente)
                        add_super_admin_email(em)
                        st.success("Permisos de Super Admin otorgados.")
                        if temp_pass:
                            st.info(f"Usuario creado. Contraseña temporal: `{temp_pass}`")
                        st.rerun()

            st.divider()
            st.subheader("Quitar permisos de Super Admin")
            current_sas = get_super_admin_emails()
            if not current_sas:
                st.caption("Sin Super Admins.")
            else:
                pick = st.selectbox("Seleccionar Super Admin", options=current_sas)
                if st.button("🗑️ Quitar permisos", use_container_width=True):
                    # Evitar dejar el sistema sin ningún super admin
                    if len(current_sas) <= 1:
                        st.error("No se puede quitar el último Super Admin.")
                    else:
                        remove_super_admin_email(pick)
                        st.success("Permisos quitados.")
                        st.rerun()

            # --- Gestión de administradores (solo Super Admin) ---
            st.divider()
            st.subheader("Gestión de Administradores")
            st.caption(
                "El **Super Admin** puede: **Suspender** (reversible) o **Anular** (desactiva) a los usuarios con rol **admin**."
            )

            admins = svc.list_admin_users(limit=500)
            if not admins:
                st.info("No hay administradores dados de alta.")
            else:
                for a in admins:
                    status_txt = "ANULADO" if int(a.get("is_active", 0)) == 0 else ("SUSPENDIDO" if int(a.get("is_suspended", 0)) == 1 else "ACTIVO")
                    head = f"#{a['id']} · {a.get('email')} · {a.get('name') or '(Sin nombre)'} · **{status_txt}**"
                    with st.expander(head):
                        st.write(f"Empresa: {a.get('company') or '-'}")
                        if a.get("phone"):
                            st.write(f"Tel: {a.get('phone')}")
                        # Evitar acciones sobre el propio Super Admin si también figura como admin
                        if str(a.get("email", "")).strip().lower() in set([e.lower() for e in get_super_admin_emails()]):
                            st.info("Este usuario tiene permisos de **Super Admin**. Para suspender/anular, primero quitá el permiso de Super Admin.")
                            continue

                        c1, c2 = st.columns(2)
                        with c1:
                            if int(a.get("is_active", 0)) == 1:
                                if int(a.get("is_suspended", 0)) == 0:
                                    if st.button("⏸️ Suspender", key=f"sus_{a['id']}", use_container_width=True):
                                        svc.set_user_suspended(int(a["id"]), True, actor_user_id=int(u["id"]))
                                        st.warning("Administrador suspendido.")
                                        st.rerun()
                                else:
                                    if st.button("▶️ Reactivar", key=f"unsus_{a['id']}", use_container_width=True):
                                        svc.set_user_suspended(int(a["id"]), False, actor_user_id=int(u["id"]))
                                        st.success("Administrador reactivado.")
                                        st.rerun()
                            else:
                                st.caption("Cuenta desactivada.")

                        with c2:
                            if int(a.get("is_active", 0)) == 1:
                                if st.button("🗑️ Anular (desactivar)", key=f"anular_{a['id']}", use_container_width=True):
                                    svc.deactivate_user(int(a["id"]), actor_user_id=int(u["id"]))
                                    st.error("Administrador anulado (cuenta desactivada).")
                                    st.rerun()

            st.divider()
            st.subheader("Moderación rápida")
            st.caption("Listado práctico para moderar publicaciones. La acción **Anular** las saca de circulación.")
            qmod = st.text_input("Buscar (título/desc/empresa/tags)", key="sa_mod_q")
            status_mod = st.selectbox(
                "Estado",
                ["(Todos)", "open", "closed", "annulled"],
                key="sa_mod_status",
                format_func=lambda x: {"(Todos)": "(Todos)", "open": "abierto", "closed": "cerrado", "annulled": "anulado"}.get(x, x),
            )
            status_param = "" if status_mod == "(Todos)" else status_mod
            reqs_mod = svc.search_requirements(q=qmod, type_="(Todos)", status=status_param, chamber_id=None, limit=50)

            st.caption(f"Mostrando {len(reqs_mod)} requerimiento(s).")
            for r in reqs_mod:
                with st.expander(f"#{r['id']} · {('NECESIDAD' if r['type']=='need' else 'OFERTA')} · {r['title']}"):
                    st.write(f"**Empresa:** {r.get('company') or '-'}")
                    st.write(f"**Cámara:** {r.get('chamber_name') or '(Sin cámara)'}")
                    st.write(f"**Estado:** { {'open':'abierto','closed':'cerrado','annulled':'anulado'}.get(r.get('status'), r.get('status')) }")
                    st.write(r.get("description") or "")
                    if r.get("status") != "annulled":
                        if st.button("⚠️ Anular requerimiento", key=f"sa_annul_{r['id']}", use_container_width=True):
                            svc.update_requirement(r["id"], status="annulled")
                            st.warning("Requerimiento anulado.")
                            st.rerun()
                    else:
                        st.info("Este requerimiento ya está **ANULADO**.")


        with t[validate_tab_idx]:
            st.header("Validar usuarios (solo Super Admin)")
            pending = svc.list_pending_users()
            if not pending:
                st.info("No hay usuarios pendientes de validación.")
            else:
                st.caption(f"Pendientes: {len(pending)}")
                for pu in pending:
                    st.markdown("---")
                    st.markdown(f"**{pu.get('name','(Sin nombre)')}** — {pu.get('company','(Sin empresa)')}")
                    st.write(f"Email: {pu.get('email')}")
                    if pu.get("phone"):
                        st.write(f"Tel: {pu.get('phone')}")
                    st.caption(f"Registrado: {pu.get('created_at')}")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Aprobar", key=f"approve_{pu['id']}", use_container_width=True):
                            svc.approve_user(int(pu["id"]), approved_by_user_id=int(u["id"]))
                            st.success("Usuario aprobado.")
                            st.rerun()
                    with c2:
                        if st.button("⛔ Rechazar", key=f"reject_{pu['id']}", use_container_width=True):
                            svc.reject_user(int(pu["id"]), rejected_by_user_id=int(u["id"]))
                            st.warning("Usuario rechazado (cuenta desactivada).")
                            st.rerun()



def _start_logout_with_backup():
    """Genera backup (si corresponde) y pide confirmación de cierre de sesión."""
    _maybe_auto_backup("logout")
    st.session_state["_logout_confirm"] = True

if __name__ == "__main__":
    main()

# --- Aviso de configuración de Email (solo admins) ---
def _email_config_warning_if_needed(role: str):
    try:
        if role in ("admin", "superadmin") and not mailer_is_configured():
            st.sidebar.warning("Email: notificaciones deshabilitadas (SMTP no configurado en Render). Ver EMAIL_SETUP_RENDER.md")
    except Exception:
        pass
