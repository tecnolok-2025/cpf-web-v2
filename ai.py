import os
import re
from typing import Any, Dict, List, Tuple


def _norm(s: str) -> str:
    """Normaliza texto para matching (minúsculas, sin acentos)."""
    import unicodedata

    s = (s or "").strip()
    s = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    return s.casefold()


def _score_keywords(qn: str, keywords: List[str]) -> int:
    """Puntúa cuántas palabras clave aparecen en el texto normalizado."""
    score = 0
    for kw in keywords:
        kwn = _norm(kw)
        if not kwn:
            continue
        if kwn in qn:
            score += 1
    return score


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


def review_requirement(title: str, description: str) -> Dict[str, Any]:
    """Revisión liviana del texto antes de publicar.

    Devuelve un dict compatible con app.py:
      - ok: bool
      - reason: str (si ok=False)
      - hits: list[str] (palabras detectadas)
      - suggested_title / suggested_description (opcional)

    Nota: NO bloquea por "tono" general; solo evita insultos claros.
    """

    t = (title or "").strip()
    d = (description or "").strip()
    text = f"{t}\n{d}".lower()

    hits = []
    for w in _OFFENSIVE_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE):
            hits.append(w)

    if hits:
        hits = sorted(set(hits))
        return {
            "ok": False,
            "reason": "El texto contiene palabras ofensivas. Por favor, revisalo y volvé a intentar.",
            "hits": hits,
        }

    # Por ahora no reescribimos contenido (solo validación).
    return {
        "ok": True,
        "suggested_title": t,
        "suggested_description": d,
        "hits": [],
    }


def _safe_get_stats() -> dict:
    """Importa services en forma diferida para evitar dependencias circulares.
    Si falla, devuelve {} (no rompe el asistente).
    """
    try:
        import services as svc  # import diferido (evita circular imports)
        try:
            stats = svc.get_stats()
            return stats if isinstance(stats, dict) else {}
        except Exception:
            return {}
    except Exception:
        return {}


def assistant_answer(q: str, role: str = "user") -> Dict[str, Any]:
    """Asistente dentro del sistema CPF.

    Objetivo: ser flexible, conversacional y práctico.
    - Si existe OPENAI_API_KEY: intenta usar OpenAI.
    - Si no existe (o falla): fallback local amigable (sin LLM).
    """

    q = (q or "").strip()
    if not q:
        return {
            "answer": "Decime qué querés hacer o entender (por ej: publicar, buscar, bandeja, panel, backups, métricas).",
            "table": None,
        }

    # Saludos y charla
    if re.fullmatch(
        r"(hola|buenas|buen día|buen dia|buenas tardes|buenas noches|hey|hello|qué tal|que tal|como va|cómo va)[.! ]*",
        q,
        re.I,
    ):
        return {
            "answer": (
                "¡Hola! 🙂\n\n"
                "Estoy acá para ayudarte a usar el sistema como si fuera un copiloto.\n"
                "Contame qué estás intentando hacer y te guío paso a paso.\n\n"
                "Ejemplos de cosas que podés preguntarme:\n"
                "• ‘¿Cómo publico una necesidad?’\n"
                "• ‘¿Cómo busco por empresa o tags?’\n"
                "• ‘No entiendo la bandeja, ¿qué significa?’\n"
                "• ‘Soy admin: ¿cómo hago un backup o recupero uno?’\n"
            ),
            "table": None,
        }

    # OpenAI (si hay API key). Si algo falla, NO rompe: cae a modo local.
    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI  # type: ignore

            client = OpenAI()
            stats = _safe_get_stats()
            system = """Sos un asistente dentro del sistema ‘CPF – Sistema de Requerimientos (sin precios)’. Ayudás a usuarios a entender y usar el sistema.

Reglas:
- Respondé SIEMPRE en español.
- Sé flexible y conversacional (estilo ChatGPT).
- Si el usuario no entiende, explicá de otra manera con ejemplos.
- Si falta info, hacé 1–2 preguntas concretas.
- No inventes datos ni funciones que no existen.
- Respuestas prácticas, con pasos.

Contexto del sistema (resumen):
- Objetivo: publicar OFERTAS/NECESIDADES y gestionar el interés/contacto **sin precios** dentro del sistema.
- Tabs principales (usuarios empresa): Navegar, Publicar, Bandeja, Panel, Interesados, Asistente IA.
- Registro: **Cámara/Institución** y **Teléfono** son obligatorios. Los usuarios nuevos quedan **Pendientes** hasta validación.
- Validación: la realiza el **Asistente** de la cámara (rol *assistant*) o el **Super Admin**. Los asistentes se habilitan por **Super Admin**.
- Asistentes: ven un **panel único** de validación, acotado a su cámara; no publican ni ven otras cámaras.
- Publicar: normalmente se pide **Categoría** y **Ubicación**. Adjuntos: **máximo 2**; el **adjunto 1 debe ser imagen** y se usa como **portada**.
- Bandeja: solicitudes de contacto recibidas (pendientes) + edición/cierre de tus publicaciones.
- Interesados: historial de solicitudes (Recibidas y Enviadas) con contacto de ambos lados cuando se acepta.
- Recuperar contraseña: botón **‘Olvidé mi contraseña’** → llega una **clave provisoria por email** (vence en minutos) → definís nueva contraseña.
- Roles: user (empresa), admin (operativo), assistant (validador por cámara), Super Admin (moderación/anulación, cámaras, backups, alta de Super Admin, validación de usuarios).
- Admin: puede ver un **indicador de almacenamiento** (uso de disco) en la barra lateral ‘Sesión’ (si está habilitado).
- Seguridad: se aceptan solo tipos de adjuntos permitidos; se bloquean ejecutables.
"""
            extra = f"Estado actual (aprox): {stats}\n" if stats else ""

            messages = [
                {"role": "system", "content": system + extra},
                {"role": "user", "content": f"Rol del usuario: {role}\nConsulta: {q}"},
            ]
            model = os.getenv("CPF_OPENAI_MODEL", "gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.5,
                max_tokens=500,
            )
            ans = (resp.choices[0].message.content or "").strip()
            if ans:
                return {"answer": ans, "table": None}
        except Exception:
            pass

    # --------- MODO LOCAL (sin LLM) ----------
    qn = _norm(q)

    # Atajo de ayuda/menú
    if any(k in qn for k in ["ayuda", "help", "que podes hacer", "que puedes hacer", "como funciona", "menu", "opciones"]):
        return {
            "answer": (
                "Puedo ayudarte con todo lo del sistema. Temas típicos:\n\n"
                "• **Publicar** (Oferta / Necesidad), adjuntos, categorías y urgencia\n"
                "• **Navegar/Buscar** (filtros por cámara, texto, tipo y estado)\n"
                "• **Bandeja** (solicitudes pendientes que recibís + edición/cierre de tus publicaciones)\n"
                "• **Interesados** (historial Recibidas/Enviadas con contacto de ambos lados)\n"
                "• **Roles** (usuario, admin, Super Admin)\n"
                "• **Moderación / Anular** requerimientos (Super Admin)\n"
                "• **Backups / Restaurar** (Super Admin)\n\n"
                "Decime cuál de estos puntos querés (por ejemplo: *‘¿qué es Interesados?’* o *‘¿cómo anulo un requerimiento?’*)."
            ),
            "table": None,
        }

    # Métricas (único caso donde devolvemos tabla)
    if any(k in qn for k in ["metric", "estad", "stats", "panel", "tablero", "indicadores"]):
        stats = _safe_get_stats()
        if stats:
            return {"answer": "Te muestro métricas generales del sistema:", "table": stats}
        return {
            "answer": "Puedo mostrar métricas, pero ahora no pude obtenerlas. Probá recargar la app.",
            "table": None,
        }

    # KB: respuestas guiadas por intención
    topics: List[Tuple[str, List[str], str]] = [
        (
            "publicar",
            ["public", "publicar", "oferta", "necesidad", "requerimiento", "nuevo", "cargar"],
            (
                "Para **publicar** una Oferta o Necesidad:\n"
                "1) Entrá a **Publicar**.\n"
                "2) Elegí el **Tipo** (Oferta / Necesidad).\n"
                "3) Completá **Título** y **Descripción** (claros y concretos).\n"
                "4) Elegí **Categoría** y completá **Ubicación** (obligatorias).\n"
                "5) Opcional: **Urgencia** y **Tags**.\n"
                "6) **Adjuntos:** máximo 2. Si se solicita **portada**, el **adjunto 1 debe ser una imagen** (JPG/JPEG/PNG/GIF/WEBP) y se verá como portada; luego podés adjuntar PDF/Word/Excel.\n"
                "7) Tocá **Publicar**.\n\n"
                "Tip: los **tags** ayudan muchísimo para que te encuentren (ej: ‘mecanizado, calderería, logística, válvulas’).\n"
                "Nota: el sistema es **sin precios**; la negociación se hace fuera del CPF."
            ),
        ),

        (
            "navegar",
            ["navegar", "buscar", "busqueda", "filtro", "filtrar", "encontr", "tags", "camara"],
            (
                "Para **buscar/navegar** publicaciones:\n"
                "1) En **Navegar**, elegí la **Cámara** (o ‘(Todas)’).\n"
                "2) Usá **Buscar** para texto libre (empresa, producto, tags, etc.).\n"
                "3) Ajustá **Tipo** (Oferta/Necesidad) y **Estado** (abierto/cerrado).\n\n"
                "Si me decís qué querés encontrar, te sugiero filtros concretos."
            ),
        ),
        (
            "bandeja",
            ["bandeja", "solicitud", "solicitudes", "contacto", "aceptar", "rechazar", "pendiente"],
            (
                "La **Bandeja** tiene 2 partes:\n"
                "• **Solicitudes recibidas**: cuando alguien te pide contacto por una de tus publicaciones (podés **Aceptar** o **Rechazar**).\n"
                "• **Mis publicaciones**: podés **editar** o **cerrar** (cambiar estado) tus ofertas/necesidades.\n\n"
                "Si aceptás una solicitud, el contacto queda visible en **Interesados** (historial), para ambos lados."
            ),
        ),
        (
            "interesados",
            ["interesad", "historial", "aceptad", "rechazad", "enviad", "recibid", "quien", "contact"],
            (
                "**Interesados** es el lugar para ver el **historial** de solicitudes de contacto (no se pierden).\n\n"
                "Dentro de Interesados tenés:\n"
                "• **Recibidas**: solicitudes que te hicieron por tus publicaciones.\n"
                "• **Enviadas**: solicitudes que vos hiciste a otros.\n\n"
                "En cada solicitud vas a ver **los dos contactos** (el tuyo y el de la otra parte), para que cualquiera de los dos pueda comunicarse.\n"
                "Estados: **Pendiente**, **Aceptada**, **Rechazada**."
            ),
        ),
        (
            "validacion_usuarios",
            ["valid", "validacion", "validar", "aprob", "aprobacion", "pendiente", "no puedo ingresar", "no me deja", "registro", "registr", "habilitar"],
            (
                "📌 **Registro con validación**\n\n"
                "Cuando te registrás, tu cuenta queda **Pendiente**.\n"
                "Hasta que un **Super Admin** la habilite, no vas a poder ingresar (vas a ver el aviso de ‘pendiente de validación’).\n\n"
                "¿Quién valida y dónde?\n"
                "• Super Admin → pestaña **Panel** → **Validar usuarios**.\n\n"
                "Si necesitás acceso urgente, avisale al administrador/superadmin para que te habilite."
            ),
        ),
        (
            "adjuntos_portada",
            ["adjunt", "adjunto", "archivo", "archivos", "pdf", "imagen", "imagenes", "portada", "subir", "cargar", "descargar"],
            (
                "📎 **Adjuntos y portada**\n\n"
                "• Máximo **2 adjuntos** por publicación.\n"
                "• Si la publicación requiere portada: el **adjunto 1** debe ser una **imagen** (JPG/JPEG/PNG/GIF/WEBP) y se muestra como **portada**.\n"
                "• El segundo adjunto puede ser un documento (PDF/Word/Excel), si lo necesitás.\n\n"
                "Consejo: usá archivos livianos (por ejemplo, imágenes optimizadas y PDFs chicos) para que suban rápido."
            ),
        ),
        (
            "disco_storage",
            ["disco", "almacen", "almacenamiento", "storage", "espacio", "ocup", "libre", "grafico", "circular", "porcentaje"],
            (
                "💾 **Espacio de disco / almacenamiento**\n\n"
                "Si sos **Admin**, en la barra lateral (**Sesión**) podés ver un indicador (gráfico) con:\n"
                "• **Ocupado** vs **Libre**\n"
                "• y el **porcentaje** de uso.\n\n"
                "Si el uso está alto, lo recomendado es:\n"
                "1) Hacer/descargar **backups** (y limpiar adjuntos viejos si corresponde).\n"
                "2) En Render, evaluar aumentar el tamaño del **disco persistente**."
            ),
        ),

        (
            "roles",
            ["rol", "roles", "permisos", "admin", "superadmin", "super admin", "moderador", "camaras"],
            (
                "En CPF hay 3 niveles prácticos:\n\n"
                "1) **Usuario (normal)**: publica ofertas/necesidades, busca, solicita contacto, responde solicitudes, y gestiona sus publicaciones.\n"
                "2) **Admin (operativo)**: es un usuario con rol *admin* para operar el sistema (por ejemplo soporte), y puede ver el **indicador de almacenamiento** en ‘Sesión’ (si está habilitado).\n"
                "3) **Super Admin**: además de lo anterior, puede **moderar/anular** requerimientos, administrar **cámaras**, hacer **backups/restaurar**, **otorgar/quitar** Super Admin y **validar usuarios nuevos** (habilitar pendientes).\n\n"
                "Nota: los usuarios recién registrados quedan **Pendientes** hasta que el Super Admin los valide."
            ),
        ),

        (
            "superadmin_alta",
            ["dar de alta", "alta", "nuevo super", "agregar super", "otorgar super", "quitar super"],
            (
                "Como **Super Admin**, en la pestaña **Dar de alta** podés:\n"
                "• **Otorgar Super Admin**: ingresás *email + nombre*.\n"
                "• **Quitar Super Admin**: revocás privilegios (evitando dejar al sistema sin ningún superadmin).\n\n"
                "Si el usuario ya está logueado, al recargar (rerun) ya ve las funciones de Super Admin."
            ),
        ),
        (
            "backups",
            ["backup", "resguardo", "copia", "restaurar", "restore", "db"],
            (
                "Tema **Backups/Resguardo** (solo Super Admin):\n"
                "• **Crear backup ahora**: genera una copia de la base (**.db**)\n"
                "• **Crear backup completo** (si está disponible): genera un **.zip** con **DB + adjuntos (uploads)**\n"
                "• **Descargar** el último backup\n"
                "• **Restaurar**: elegir un backup o subir un **.db** (y, si corresponde, restaurar adjuntos)\n\n"
                "En Render, conviene usar disco persistente y/o descargar backups para no perder datos en redeploy."
            ),
        ),
    ]

    best = None
    best_score = 0
    for _name, kws, ans in topics:
        sc = _score_keywords(qn, kws)
        if sc > best_score:
            best_score = sc
            best = (ans, _name)

    # Umbral bajo: si al menos matchea 1 keyword relevante, respondemos.
    if best and best_score >= 1:
        return {"answer": best[0], "table": None}

    return {
        "answer": (
            "Dale. Para ayudarte bien, decime qué querés lograr o qué pantalla estás mirando.\n\n"
            "Ejemplos: ‘¿qué es Interesados?’, ‘¿cómo acepto una solicitud?’, ‘¿cómo anulo un requerimiento?’."
        ),
        "table": None,
    }
