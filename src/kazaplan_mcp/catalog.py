"""Catalogue Kazaplan (partenaire Leroy Merlin) : téléchargement, index local, recherche.

Au premier lancement, le serveur télécharge les sources du CDN, construit index.json et templates.json
dans le dossier de données (paths.CATALOG) puis jette les sources (≈ 350 Mo).

kazaplan-mcp catalog                   -> même chose, à la demande (forcer une mise à jour)
python -m kazaplan_mcp.catalog fetch   -> télécharge et garde les sources (analyse du catalogue)
python -m kazaplan_mcp.catalog build   -> reconstruit l'index à partir des sources gardées
"""

import json
import re
import shutil
import sys
import threading
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

import httpx

from . import paths

CACHE = paths.CATALOG
PARTNER = "595a5d833027c"
CDN = "https://cdn.kazaplan.com/catalogs"

SOURCES = {
    "attributes.json": f"{CDN}/common/production/attributes.json",
    "product-families-model.json": f"{CDN}/common/production/product-families-model.json",
    "models.json": f"{CDN}/{PARTNER}/production/models.json",
    "models-prices.json": f"{CDN}/{PARTNER}/production/models-prices.json",
    "models-archived.json": f"{CDN}/{PARTNER}/archives/models.json",
    "materials.json": f"{CDN}/{PARTNER}/production/materials.json",
    "materials-prices.json": f"{CDN}/{PARTNER}/production/materials-prices.json",
    "materials-archive.json": f"{CDN}/{PARTNER}/production/materials-archive.json",
    "kitchen-blocks.json": f"{CDN}/{PARTNER}/production/kitchen-blocks.json",
    "kitchen-styles.json": f"{CDN}/{PARTNER}/production/kitchen-styles.json",
    "brands.json": f"{CDN}/{PARTNER}/production/brands.json",
    "menus.json": f"{CDN}/{PARTNER}/production/menus.json",
    "partner.json": f"{CDN}/{PARTNER}/production/partner.json",
    "room-configurator-config.json": f"{CDN}/{PARTNER}/production/plugins/room-configurator/config.json",
    "locales-fr.json": "https://planner.kazaplan.com/planner/locales/fr.json",
}

# Menus "decorate" dont les matériaux vont au sol / au mur.
FLOOR_MENUS = {"CARRELAGE_SOL", "PARQUET", "PVC", "SOL_EXTERIEUR", "MOQUETTE_JONC_SISAL"}
WALL_MENUS = {"CARRELAGE_MUR", "PEINTURE", "PAPIER_PEINT", "BRIQUETTE_PAREMENT", "FACADE"}
# Champ `color` des matériaux (ex. "GREY|GREEN"), renseigné pour une partie des peintures seulement.
MATERIAL_COLORS = {
    "WHITE": "Blanc",
    "BEIGE": "Beige",
    "BROWN": "Marron",
    "GREY": "Gris",
    "BLACK": "Noir",
    "BLUE": "Bleu",
    "GREEN": "Vert",
    "YELLOW": "Jaune",
    "ORANGE": "Orange",
    "RED": "Rouge",
    "PINK": "Rose",
    "PURPLE": "Violet",
}


def fetch(dest: Path = CACHE, log=print):
    dest.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=300, follow_redirects=True) as c:
        for name, url in SOURCES.items():
            with c.stream("GET", url) as r:
                r.raise_for_status()
                with (dest / name).open("wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            log(f"{name}: {(dest / name).stat().st_size} octets")


def ready() -> bool:
    return (CACHE / "index.json").exists() and (CACHE / "templates.json").exists()


def ensure(force: bool = False, log=print):
    """Télécharge les sources dans un dossier temporaire, construit l'index, puis supprime les sources."""
    if ready() and not force:
        return
    tmp = CACHE.parent / "catalog-download"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        fetch(tmp, log)
        build(tmp, log)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    index.cache_clear()
    by_id.cache_clear()
    templates.cache_clear()


_download: dict = {"thread": None, "error": None}


def ensure_in_background():
    """Au démarrage du serveur : le téléchargement prend quelques minutes, les outils restent disponibles."""
    if ready():
        return

    def run():
        try:
            ensure(log=lambda msg: print(msg, file=sys.stderr))
        except Exception as e:
            _download["error"] = e

    _download["thread"] = threading.Thread(target=run, name="catalog-download", daemon=True)
    _download["thread"].start()


def _missing() -> FileNotFoundError:
    thread, error = _download["thread"], _download["error"]
    if thread and thread.is_alive():
        return FileNotFoundError(
            "Catalogue en cours de téléchargement (premier lancement, quelques minutes) : réessayer bientôt"
        )
    if error:
        return FileNotFoundError(f"Catalogue non téléchargé ({error}) : lancer `kazaplan-mcp catalog`")
    return FileNotFoundError(f"Catalogue absent de {CACHE} : lancer `kazaplan-mcp catalog`")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _stem(tok: str) -> str:
    if len(tok) > 3 and tok[-1] in "sx":
        return tok[:-1]
    return tok


def _fr(label) -> str:
    if not isinstance(label, dict):
        return label or ""
    return label.get("fr_FR") or label.get("en_US") or ""


def _load(src: Path, name: str):
    return json.loads((src / name).read_text(encoding="utf-8"))


def _usual_price(per_store: dict | None):
    if not per_store:
        return None
    prices = [v.get("price") for v in per_store.values() if v.get("price")]
    return Counter(prices).most_common(1)[0][0] if prices else None


def _menu_paths(menus):
    by_id = {m["id"]: m for m in menus}

    def chain(m):
        out = []
        while m:
            out.append(m)
            parents = m.get("parents") or []
            m = by_id.get(parents[0]["id"]) if parents else None
        return list(reversed(out))

    item_menus: dict[str, list[dict]] = {}
    for m in menus:
        action = m.get("action") or {}
        for it in (action.get("params") or {}).get("items", []):
            c = chain(m)
            item_menus.setdefault(it["id"], []).append(
                {
                    "path": " > ".join(_fr(x["label"]) for x in c),
                    "codes": [x["code"] for x in c],
                    "menuType": m["menuType"],
                }
            )
    return item_menus


def _attribute_labels(attributes):
    """{CODE: {value_code: libellé fr}}, fusionné sur tous les attributs de même code."""
    out: dict[str, dict[str, str]] = {}
    for a in attributes:
        vals = out.setdefault(a["code"], {})
        for v in a.get("values") or []:
            lab = _fr(v.get("label"))
            if lab:
                vals.setdefault(str(v["code"]), lab)
    return out


def _structures(model) -> list:
    md = model["data"]["metadata"]
    if isinstance(md, list):
        return md
    if isinstance(md, dict):
        return md.get("structures") or []
    return []


def _placeable(model) -> bool:
    structs = _structures(model)
    return (
        model["type"] == "prefab"
        and bool(structs)
        and all(s["__name__"] == "model.model-structure" for s in structs)
    )


def build(src: Path = CACHE, log=print):
    menus = _load(src, "menus.json")["items"]
    item_menus = _menu_paths(menus)
    attr = _attribute_labels(_load(src, "attributes.json")["items"])
    color_names = {**attr.get("COLOR_MATERIAL", {}), **attr.get("COLOR", {})}
    brands_raw = _load(src, "brands.json")
    brands = {b["id"]: b["name"] for b in brands_raw.get("brands", [])}

    models_prices = _load(src, "models-prices.json")
    index, templates = [], {}
    for m in _load(src, "models.json")["items"]:
        if m["isArchived"]:
            continue
        mens = item_menus.get(m["id"], [])
        if m["searchDisabled"] and not mens:
            continue
        a = m["attribute"]
        dims = m["data"]["dimensions"] or {}
        placeable = _placeable(m)
        if placeable:
            templates[m["id"]] = _structures(m)
        index.append(
            {
                "id": m["id"],
                "kind": "model",
                "type": m["type"],
                "label": _fr(m["label"]),
                "menus": [x["path"] for x in mens],
                "menuCodes": sorted({c for x in mens for c in x["codes"]}),
                "w": dims.get("width"),
                "d": dims.get("depth"),
                "h": dims.get("height"),
                "elevation": m["data"].get("elevation") or 0,
                "magnetism": a.get("MAGNETISM") or [],
                "style": [attr.get("STYLE", {}).get(s, s) for s in a.get("STYLE") or []],
                "colors": sorted({color_names.get(c, c) for c in a.get("COLOR") or []}),
                "materials": [attr.get("MATERIAL", {}).get(s, s) for s in a.get("MATERIAL") or []],
                "brand": brands.get(a.get("brand")),
                "family": m.get("productFamilyCode"),
                "price": _usual_price(models_prices.get(m["id"])),
                "url": m["data"].get("url"),
                "placeable": placeable,
                "_asset3d": m["data"].get("asset3d"),
            }
        )

    mat_prices = _load(src, "materials-prices.json")
    for m in _load(src, "materials.json")["items"]:
        if m.get("isArchived"):
            continue
        mens = item_menus.get(m["id"], [])
        codes = {c for x in mens for c in x["codes"]}
        usage = []
        if codes & FLOOR_MENUS:
            usage.append("floor")
        if codes & WALL_MENUS:
            usage.append("wall")
        a = m.get("attribute") or {}
        index.append(
            {
                "id": m["id"],
                "kind": "material",
                "type": m["data"].get("materialType"),
                "label": _fr(m["label"]),
                "menus": [x["path"] for x in mens],
                "menuCodes": sorted(codes),
                "usage": usage,
                "colors": sorted({MATERIAL_COLORS.get(c, c) for c in (m.get("color") or "").split("|") if c}),
                "brand": brands.get(a.get("brand")),
                "packagingContent": a.get("packagingContent"),
                "price": _usual_price(mat_prices.get(m["id"])),
                "url": m["data"].get("url"),
            }
        )

    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    (CACHE / "templates.json").write_text(json.dumps(templates, ensure_ascii=False), encoding="utf-8")
    n_models = sum(1 for x in index if x["kind"] == "model")
    log(f"index.json : {n_models} modèles ({len(templates)} plaçables), {len(index) - n_models} matériaux")


@lru_cache(maxsize=1)
def index() -> list[dict]:
    path = CACHE / "index.json"
    if not path.exists():
        raise _missing()
    items = json.loads(path.read_text(encoding="utf-8"))
    for it in items:
        hay = " ".join(
            [
                it["label"],
                *it["menus"],
                *it.get("style", []),
                *it.get("colors", []),
                *it.get("materials", []),
                it.get("brand") or "",
                it.get("type") or "",
            ]
        )
        it["_tokens"] = {_stem(t) for t in norm(hay).split()}
    return items


@lru_cache(maxsize=1)
def by_id() -> dict[str, dict]:
    return {it["id"]: it for it in index()}


@lru_cache(maxsize=1)
def templates() -> dict[str, list]:
    path = CACHE / "templates.json"
    if not path.exists():
        raise _missing()
    return json.loads(path.read_text(encoding="utf-8"))


def get(item_id: str) -> dict | None:
    return by_id().get(item_id)


def public(it: dict) -> dict:
    return {k: v for k, v in it.items() if not k.startswith("_") and v not in (None, [], "")}


def search(
    query: str = "",
    kind: str | None = None,
    category: str | None = None,
    max_w: float | None = None,
    max_d: float | None = None,
    max_h: float | None = None,
    style: str | None = None,
    color: str | None = None,
    usage: str | None = None,
    placeable_only: bool = True,
    limit: int = 20,
) -> list[dict]:
    q = [_stem(t) for t in norm(query).split()]
    cat = norm(category) if category else None
    out = []
    for it in index():
        if kind and it["kind"] != kind:
            continue
        if it["kind"] == "model" and placeable_only and not it["placeable"]:
            continue
        if cat and not any(cat in norm(p) for p in it["menus"] + it["menuCodes"]):
            continue
        if usage and usage not in it.get("usage", [usage]):
            continue
        if max_w is not None and (it.get("w") or 0) > max_w:
            continue
        if max_d is not None and (it.get("d") or 0) > max_d:
            continue
        if max_h is not None and (it.get("h") or 0) > max_h:
            continue
        if style and norm(style) not in norm(" ".join(it.get("style", []))):
            continue
        if color and norm(color) not in norm(" ".join(it.get("colors", []) + [it["label"]])):
            continue
        toks = it["_tokens"]
        hits = sum(1 for t in q if t in toks or any(x.startswith(t) for x in toks))
        if q and hits < len(q):
            continue
        label_list = [_stem(t) for t in norm(it["label"]).split()]
        menu_toks = {_stem(t) for t in norm(" ".join(it["menus"])).split()}
        score = (
            sum(2 for t in q if t in label_list)
            + sum(2 for t in q if t in menu_toks)
            + (3 if q and label_list and label_list[0] == q[0] else 0)
            + (1 if it["menus"] else 0)
        )
        out.append((score, it))
    out.sort(key=lambda x: (-x[0], x[1].get("price") or 1e9))
    return [public(it) for _, it in out[:limit]]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "fetch":
        fetch()
    elif cmd == "build":
        build()
    else:
        print(__doc__)
        sys.exit(1)
