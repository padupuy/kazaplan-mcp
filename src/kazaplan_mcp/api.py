"""Accès à l'API Kazaplan (lecture / sauvegarde d'un plan .kzp)."""

import os
import re
import time
from pathlib import Path

import httpx

from . import paths

API = os.environ.get("KZ_API_URL", "https://api.kazaplan.com")
PARTNER_ID = "7"
PLAN_ID = re.compile(r"[0-9]+")
BACKUPS = paths.BACKUPS


class ApiError(RuntimeError):
    pass


def _token() -> str:
    tok = os.environ.get("KZ_TOKEN")
    if not tok:
        raise ApiError("Variable d'environnement KZ_TOKEN absente (JWT Kazaplan)")
    return tok


def check_plan_id(plan_id: str | None) -> str:
    if not plan_id or not PLAN_ID.fullmatch(str(plan_id)):
        raise ApiError(f"Identifiant de plan invalide : {plan_id!r} (nombre attendu, ex. 12345678)")
    return str(plan_id)


def allowed_plan_ids() -> set[str]:
    return {x.strip() for x in os.environ.get("KZ_ALLOWED_PLANS", "").split(",") if x.strip()}


def backup(plan_id: str | None, data: bytes, tag: str) -> Path:
    name = check_plan_id(plan_id) if plan_id else "local"
    BACKUPS.mkdir(parents=True, exist_ok=True)
    path = BACKUPS / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}-{tag}.kzp"
    path.write_bytes(data)
    return path


def _find_file_url(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("fileUrl"), str):
            return obj["fileUrl"]
        for v in obj.values():
            if u := _find_file_url(v):
                return u
    elif isinstance(obj, list):
        for v in obj:
            if u := _find_file_url(v):
                return u
    return None


def download(plan_id: str) -> tuple[bytes, dict]:
    """GET /plans/{id} -> fileUrl -> .kzp."""
    plan_id = check_plan_id(plan_id)
    headers = {"Authorization": f"Bearer {_token()}"}
    with httpx.Client(timeout=60, follow_redirects=True) as c:
        r = c.get(f"{API}/plans/{plan_id}", headers=headers)
        if r.status_code >= 400:
            raise ApiError(f"GET /plans/{plan_id} : HTTP {r.status_code} {r.text[:300]}")
        meta = r.json()
        url = _find_file_url(meta)
        if not url:
            raise ApiError(f"Pas de fileUrl dans la réponse : {list(meta)[:20]}")
        f = c.get(url)
        f.raise_for_status()
        return f.content, meta


def upload(plan_id: str, title: str, data: bytes) -> dict:
    plan_id = check_plan_id(plan_id)
    if plan_id not in allowed_plan_ids():
        raise ApiError(
            f"Plan {plan_id} hors liste blanche : l'ajouter à KZ_ALLOWED_PLANS pour autoriser l'écriture"
        )
    with httpx.Client(timeout=120) as c:
        r = c.post(
            f"{API}/plans/save/{plan_id}",
            headers={"Authorization": f"Bearer {_token()}"},
            data={"title": title, "userJourney": "virtualHome", "id": plan_id, "partnerId": PARTNER_ID},
            files={"file": (f"{plan_id}.kzp", data, "application/octet-stream")},
        )
    if r.status_code >= 400:
        raise ApiError(f"POST /plans/save/{plan_id} : HTTP {r.status_code} {r.text[:300]}")
    return r.json()
