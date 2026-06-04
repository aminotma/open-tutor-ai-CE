"""Register OTAI tools and model system prompt in the Open WebUI database at server startup.

Called once from main.startup_db_client(). All errors are silenced so a
registration failure never blocks the server from starting.
"""
from __future__ import annotations

import logging
import os
import time
import types

log = logging.getLogger(__name__)


def register_otai_tools() -> None:
    """Upsert all OTAI tools into the Open WebUI tools table."""
    try:
        _ensure_database_url()
        from open_webui.models.tools import Tools, ToolForm, ToolMeta  # noqa: PLC0415
        from open_webui.models.users import Users                       # noqa: PLC0415
        from open_tutorai.tools.owui_tools import TOOLS_MANIFEST        # noqa: PLC0415

        admin = _get_admin(Users)
        if admin is None:
            log.warning("[OTAI] tools_registrar: no user found — skipping registration")
            return

        for entry in TOOLS_MANIFEST:
            try:
                specs = _extract_specs(entry["code"])
                _upsert_tool(
                    Tools=Tools,
                    ToolForm=ToolForm,
                    ToolMeta=ToolMeta,
                    tool_id=entry["id"],
                    name=entry["name"],
                    description=entry["description"],
                    code=entry["code"],
                    specs=specs,
                    user_id=admin.id,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("[OTAI] tools_registrar: failed to register %s: %s", entry["id"], exc)

        log.info("[OTAI] tools_registrar: registration complete (%d tools)", len(TOOLS_MANIFEST))

    except Exception as exc:  # noqa: BLE001
        log.warning("[OTAI] tools_registrar: registration skipped — %s", exc)


_OTAI_SYSTEM_PROMPT = """\
Tu es OpenTutorAI, un tuteur adaptatif intelligent. Tu disposes d'outils internes \
que tu DOIS utiliser en priorité sur toute ressource externe :

- Quand l'utilisateur veut tester ou exécuter du SQL → utilise toujours l'outil \
**OpenTutorAI — Requêtes SQL** (tables : Customers, Products, Orders, Employees). \
Ne suggère jamais W3Schools ou un éditeur externe.
- Quand l'utilisateur veut exécuter du Python → utilise **OpenTutorAI — Exécution de code**.
- Quand l'utilisateur veut tracer une courbe ou une chronologie → utilise **OpenTutorAI — Graphique**.
- Quand l'utilisateur veut calculer une expression mathématique → utilise **OpenTutorAI — Calcul symbolique**.
- Quand tu as besoin d'informations externes → utilise **OpenTutorAI — Recherche web**.

Réponds dans la langue de l'utilisateur. Sois pédagogique et concis.\
"""


def configure_otai_model_system_prompt() -> None:
    """Inject the OTAI system prompt on every model that has none configured."""
    try:
        _ensure_database_url()
        from open_webui.models.models import Models  # noqa: PLC0415

        models = Models.get_all_models()
        updated = 0
        for model in models:
            params = model.params.model_dump() if model.params else {}
            if params.get("system", "").strip():
                continue  # already has a system prompt — don't override
            params["system"] = _OTAI_SYSTEM_PROMPT
            Models.update_model_by_id(model.id, {
                "params":     params,
                "updated_at": int(time.time()),
            })
            updated += 1

        if updated:
            log.info("[OTAI] tools_registrar: system prompt set on %d model(s)", updated)

    except Exception as exc:  # noqa: BLE001
        log.warning("[OTAI] tools_registrar: system prompt configuration skipped — %s", exc)


# ── Internals ─────────────────────────────────────────────────────────────────

def _ensure_database_url() -> None:
    """Set DATABASE_URL from DATA_DIR if not already present in the environment."""
    if os.getenv("DATABASE_URL"):
        return
    data_dir = os.getenv("DATA_DIR", "")
    if data_dir:
        os.environ["DATABASE_URL"] = f"sqlite:///{data_dir}/webui.db"


def _get_admin(Users) -> object | None:  # noqa: N803
    """Return the first available user, preferring admins."""
    try:
        # Strategy 1 — first user created (lowest ID, usually the admin)
        users = Users.get_users(skip=0, limit=1)
        if users:
            return users[0]
    except Exception:  # noqa: BLE001
        pass

    try:
        # Strategy 2 — scan first 20 users for an admin role
        users = Users.get_users(skip=0, limit=20)
        for u in users:
            if getattr(u, "role", "") == "admin":
                return u
        if users:
            return users[0]
    except Exception:  # noqa: BLE001
        pass

    return None


def _upsert_tool(
    *,
    Tools,       # noqa: N803
    ToolForm,    # noqa: N803
    ToolMeta,    # noqa: N803
    tool_id: str,
    name: str,
    description: str,
    code: str,
    specs: list[dict],
    user_id: str,
) -> None:
    existing = Tools.get_tool_by_id(tool_id)
    if existing is None:
        form = ToolForm(
            id=tool_id,
            name=name,
            content=code,
            meta=ToolMeta(description=description),
            access_control=None,
        )
        Tools.insert_new_tool(user_id, form, specs)
        log.debug("[OTAI] tools_registrar: created tool %s", tool_id)
    else:
        Tools.update_tool_by_id(tool_id, {
            "name":    name,
            "content": code,
            "specs":   specs,
            "meta":    {"description": description, "manifest": {}},
            "updated_at": int(time.time()),
        })
        log.debug("[OTAI] tools_registrar: updated tool %s", tool_id)


def _extract_specs(code: str) -> list[dict]:
    """Exec the tool code and return its OpenAI function-calling specs."""
    from open_webui.utils.tools import get_tools_specs  # noqa: PLC0415

    module = types.ModuleType("_otai_spec_probe")
    exec(code, module.__dict__)  # noqa: S102
    tool_cls = getattr(module, "Tools", None)
    if tool_cls is None:
        raise ValueError("No 'Tools' class found in tool code")
    return get_tools_specs(tool_cls())
