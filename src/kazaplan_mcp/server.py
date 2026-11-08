"""Serveur MCP (stdio) pour piloter un plan Kazaplan / Leroy Merlin.

Unités : cm, angles en degrés. Coordonnées du plan 2D (x, y) telles que renvoyées par kz_summary.
"""

import sys
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import api, catalog, circulation, paths, sketch
from .plan import Plan, PlanError

SKETCHES = paths.SKETCHES

mcp = FastMCP(
    "kazaplan",
    instructions=(
        "Pilote un plan 3D Kazaplan (planner Leroy Merlin). Workflow : kz_open -> kz_summary -> "
        "kz_room_geometry -> kz_search_catalog -> kz_place / kz_set_material -> kz_save. "
        "Toutes les cotes sont en cm. Rien n'est envoyé au serveur avant kz_save."
    ),
)

STATE: dict = {"plan": None, "plan_id": None, "source": None, "title": None}


def _plan() -> Plan:
    if STATE["plan"] is None:
        raise ToolError("Aucun plan ouvert : appeler kz_open d'abord")
    return STATE["plan"]


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (PlanError, api.ApiError, OSError, ValueError) as e:
        raise ToolError(str(e)) from e


def _public_geometry(geo: dict) -> dict:
    return {k: v for k, v in geo.items() if not k.startswith("_")}


@mcp.tool
def kz_open(plan_id: str | None = None, path: str | None = None) -> dict:
    """Ouvre un plan : depuis l'API Kazaplan (plan_id, nécessite KZ_TOKEN) ou un fichier .kzp local (path).
    Pour un fichier local, plan_id (cible d'un futur kz_save) vaut par défaut le début du nom de fichier
    (« 12345678-20261014-212320-orig.kzp » -> « 12345678 »).
    Une copie de sauvegarde du .kzp d'origine est écrite dans backups/."""
    if path:
        data = _run(Path(path).expanduser().read_bytes)
        if not plan_id:
            prefix = Path(path).stem.split("-")[0]
            plan_id = prefix if api.PLAN_ID.fullmatch(prefix) else None
        source, title = str(path), None
    elif plan_id:
        data, meta = _run(api.download, plan_id)
        source, title = f"api:{plan_id}", meta.get("title")
    else:
        raise ToolError("Fournir plan_id ou path")
    plan = _run(Plan.from_bytes, data)
    backup = _run(api.backup, plan_id, data, "orig")
    STATE.update(plan=plan, plan_id=plan_id, source=source, title=title)
    s = plan.summary()
    return {
        "planId": plan_id,
        "title": title or s["title"],
        "source": source,
        "backup": str(backup),
        "rooms": [r["name"] for r in s["rooms"]],
        "objects": len(s["objects"]),
    }


@mcp.tool
def kz_save(title: str | None = None, out_path: str | None = None) -> dict:
    """Enregistre le plan (titre par défaut : celui du plan côté serveur).
    Avec out_path : écrit seulement un .kzp local (aucun envoi).
    Sinon : POST sur l'API (plan_id doit figurer dans KZ_ALLOWED_PLANS). Le fichier envoyé est
    aussi archivé dans backups/."""
    plan = _plan()
    data = _run(plan.to_bytes)
    if out_path:
        target = Path(out_path).expanduser()
        if target.suffix.lower() != ".kzp" or target.is_symlink():
            raise ToolError("out_path doit être un fichier .kzp (pas un lien symbolique)")
        _run(target.write_bytes, data)
        return {"written": out_path, "bytes": len(data), "geometryChanged": plan.geometry_dirty}
    plan_id = STATE["plan_id"]
    if not plan_id:
        raise ToolError("Plan ouvert sans identifiant numérique : rouvrir avec kz_open(path=…, plan_id=…)")
    _run(api.backup, plan_id, data, "sent")
    res = _run(
        api.upload, plan_id, title or STATE["title"] or plan.project.get("title") or "Mon projet", data
    )
    return {
        "planId": plan_id,
        "bytes": len(data),
        "geometryChanged": plan.geometry_dirty,
        "response": {k: v for k, v in res.items() if k != "fileUrl"} if isinstance(res, dict) else res,
    }


@mcp.tool
def kz_copy_plan(source_plan_id: str, target_plan_id: str, title: str | None = None) -> dict:
    """Duplique un plan : copie le .kzp de source_plan_id dans target_plan_id, puis l'ouvre.
    L'API ne permet pas (encore) de créer un plan : créer d'abord un plan vide sur leroymerlin.fr
    (Mon projet 3D), noter son id et l'ajouter à KZ_ALLOWED_PLANS. Le contenu de la cible est
    remplacé ; il est archivé dans backups/ avant l'envoi. Usage type : faire une copie de travail
    du plan réel avant de le modifier."""
    source = _run(api.check_plan_id, source_plan_id)
    target = _run(api.check_plan_id, target_plan_id)
    if source == target:
        raise ToolError("Source et cible identiques")
    if target not in api.allowed_plan_ids():
        raise ToolError(f"Plan cible {target} hors liste blanche : l'ajouter à KZ_ALLOWED_PLANS")
    data, meta = _run(api.download, source)
    plan = _run(Plan.from_bytes, data)
    old, old_meta = _run(api.download, target)
    before = _run(api.backup, target, old, "before-copy")
    title = title or f"{meta.get('title') or 'Mon projet'} (copie)"
    _run(api.backup, target, data, "sent")
    res = _run(api.upload, target, title, data)
    STATE.update(plan=plan, plan_id=target, source=f"api:{source}", title=title)
    return {
        "source": source,
        "planId": target,
        "title": title,
        "replacedTitle": old_meta.get("title"),
        "backup": str(before),
        "rooms": [r["name"] for r in plan.summary()["rooms"]],
        "updatedAt": res.get("updatedAt") if isinstance(res, dict) else None,
    }


@mcp.tool
def kz_summary() -> dict:
    """Résumé du plan : pièces (surface, sol), murs, ouvertures, objets posés (cotes, pièce), piscines."""
    return _run(_plan().summary)


@mcp.tool
def kz_room_geometry(room: str) -> dict:
    """Géométrie d'une pièce (nom, type ou id) : arêtes du contour intérieur avec longueur, normale
    vers l'intérieur, mur porteur, ouvertures (abscisses from/to depuis le début de l'arête) et segments
    libres `free` (portes + 5 cm de marge et fenêtres exclues), zones de débattement des portes,
    surface totale et utile (hors objets posés au sol)."""
    return _public_geometry(_run(_plan().room_geometry, room))


@mcp.tool
def kz_check_room(room: str) -> dict:
    """Contrôle la circulation d'une pièce. issues : meubles dont le dégagement est sous la cote (derrière une
    chaise 75, devant un canapé 60 jusqu'à la table basse, autour d'une table à manger 110 sans compter les
    chaises (90 pour un îlot ou une table haute), devant une armoire 75, un buffet 60, un meuble de cuisine
    90, de chaque côté d'un lit double 60).
    paths : depuis la porte de la pièce, chaque autre porte, porte-fenêtre ou passage ouvert est-il
    atteignable par un chemin de 60 cm (width60) et de 90 cm (width90) ?"""
    return _run(circulation.check, _plan(), room)


@mcp.tool
def kz_sketch(room: str | None = None, decor_path: str | None = None, out_path: str | None = None) -> dict:
    """Plan SVG vu de dessus d'une pièce (ou du bâtiment principal si room est absent), comme le plan 2D
    du planner : murs, portes, fenêtres, tapis, meubles (une lettre par modèle, cf. legend), luminaires.
    decor_path (DECOR.md) : trace en liseré la peinture de chaque mur aux couleurs de la palette.
    Écrit le fichier (out_path en .svg, sinon dans le dossier de données) et renvoie son chemin ;
    wall / on_top / ceiling listent les objets muraux, posés sur un meuble, au plafond ;
    schedule = nomenclature (code, libellé, dimensions, emplacement), un élément par objet."""
    paints = sketch.paint_colors(sketch.read_decor(Path(decor_path))) if decor_path else None
    out = _run(sketch.render, _plan(), room, paints)
    path = Path(out_path).expanduser() if out_path else SKETCHES / f"{sketch.slug(room or 'maison')}.svg"
    if path.suffix.lower() != ".svg" or path.is_symlink():
        raise ToolError("out_path doit être un fichier .svg (pas un lien symbolique)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(out.pop("svg"))
    return {"svg_path": str(path.resolve()), **out}


@mcp.tool
def kz_board(decor_path: str) -> dict:
    """Livrable de la maison pour le plan ouvert : écrit à côté du DECOR.md un PLANCHES.md (vue d'ensemble,
    nuancier, tableau des pièces, puis par pièce du DECOR.md : plan coté, deux coupes, revêtements,
    nomenclature) et ses dossiers plans/ et swatches/. À relancer après chaque kz_save."""
    return _run(sketch.write_board, _plan(), Path(decor_path).expanduser())


@mcp.tool
def kz_search_catalog(
    query: str = "",
    category: str | None = None,
    max_w: float | None = None,
    max_d: float | None = None,
    max_h: float | None = None,
    style: str | None = None,
    color: str | None = None,
    kind: str | None = "model",
    usage: str | None = None,
    limit: int = 15,
) -> list[dict]:
    """Recherche dans le catalogue Leroy Merlin local (plein texte FR, sans accents requis).
    kind : "model" (meubles/objets) ou "material" (revêtements). category : libellé ou code de menu
    (ex. "Baignoires", "SDB_BAIGNOIRES", "Canapés"). usage (matériaux) : "floor" ou "wall".
    style : Design, Essential, Natural, Industrial, Boheme, Neoclassic, Country.
    w = largeur (face avant), d = profondeur, h = hauteur, en cm ; price en € TTC."""
    return _run(
        catalog.search,
        query,
        kind=kind,
        category=category,
        max_w=max_w,
        max_d=max_d,
        max_h=max_h,
        style=style,
        color=color,
        usage=usage,
        limit=limit,
    )


@mcp.tool
def kz_catalog_item(item_id: str) -> dict:
    """Fiche d'un article du catalogue (model-… ou material-…)."""
    it = _run(catalog.get, item_id)
    if not it:
        raise ToolError(f"Article inconnu : {item_id}")
    return catalog.public(it)


@mcp.tool
def kz_place(
    model_id: str,
    room: str | None = None,
    against_wall: int | None = None,
    offset: float | None = None,
    rotation: float | None = None,
    x: float | None = None,
    y: float | None = None,
    center: bool = False,
    under_opening: str | None = None,
    width: float | None = None,
    depth: float | None = None,
    height: float | None = None,
    gap: float = 1.0,
    force: bool = False,
    elevation: float | None = None,
    on_top_of: str | None = None,
) -> dict:
    """Pose un modèle du catalogue dans une pièce, avec contrôle de collision (murs, objets,
    débattement des portes, fenêtres masquées).
    - Par défaut : dos contre le plus long mur libre qui convient.
    - against_wall : index d'arête (cf. kz_room_geometry) ; offset : distance en cm entre le début
      de l'arête et le bord de l'objet (sinon centré dans le plus grand segment libre).
    - center=True : au centre de la pièce. x, y : centre imposé (coordonnées plan).
    - under_opening : id d'une fenêtre ; centre l'objet sous elle, dos au mur (radiateurs).
    - room absent : pose en extérieur, au niveau du terrain ; x, y obligatoires, contrôle des murs traversés.
    - width / depth / height : redimensionne le modèle (cm), ex. pergola sur mesure.
    - gap : distance dos du modèle / mur (cm, défaut 1) ; ex. 59 pour poser des portes de dressing
      devant des caissons de 58 cm. Les modèles NO_COLLISION (portes de dressing…) peuvent chevaucher.
    - rotation : rotation supplémentaire en degrés (sens trigonométrique) ; avec x, y : angle absolu
      (la face avant regarde vers rotation + 90°).
    - force=True : pose même en cas de collision (renvoyée dans warnings).
    - elevation : hauteur du bas de l'objet au-dessus du sol (cm), au lieu de celle du catalogue
      (miroir à 120, applique à 170, étagère murale…).
    - on_top_of : id d'un objet posé ; pose dessus (lampe sur un buffet, vase sur une table), centré
      sur lui sauf x, y fournis ; avec elevation, pose à cette hauteur (lit : le dessus du matelas,
      pas la tête de lit)."""
    return _run(
        _plan().place,
        model_id,
        room,
        against_wall=against_wall,
        offset=offset,
        rotation=rotation,
        x=x,
        y=y,
        center=center,
        under_opening=under_opening,
        width=width,
        depth=depth,
        height=height,
        gap=gap,
        force=force,
        elevation=elevation,
        on_top_of=on_top_of,
    )


@mcp.tool
def kz_add_walls(
    points: list[list[float]], thickness: float = 20, height: float | None = None, closed: bool = False
) -> dict:
    """Ajoute une chaîne de murs reliés passant par `points` ([[x, y], …], cm).
    Épaisseurs usuelles : 30 extérieur, 7 cloison. Une extrémité libre posée sur un mur existant
    (axe ou face, à ½ épaisseur + 4 cm près) s'y raccorde : en T sur le flanc, en coin sur une
    extrémité libre. Les faces (wall.pane) des nouveaux murs sont créées par le planner à l'ouverture.
    Aucune pièce n'est créée : le planner la détecte à la prochaine ouverture + enregistrement,
    ensuite seulement la nommer avec kz_set_room."""
    return {"wallIds": _run(_plan().add_walls, points, thickness=thickness, height=height, closed=closed)}


@mcp.tool
def kz_add_opening(
    wall_id: str,
    kind: str = "door",
    offset: float | None = None,
    width: float | None = None,
    height: float | None = None,
    elevation: float | None = None,
    nb_casement: int | None = None,
) -> dict:
    """Ajoute une ouverture sur un mur. kind : "door" (90×215 par défaut) ou "casement-window"
    (100×135, allège 95). offset : distance en cm entre le début du mur et le bord de l'ouverture
    (sinon centrée)."""
    return {
        "id": _run(
            _plan().add_opening,
            wall_id,
            kind=kind,
            offset=offset,
            width=width,
            height=height,
            elevation=elevation,
            nb_casement=nb_casement,
        )
    }


@mcp.tool
def kz_set_room(room: str, type: str | None = None, name: str | None = None) -> dict:
    """Renomme et/ou change le type d'une pièce existante (nom, type ou id).
    Ne crée jamais de pièce : après kz_add_walls, ouvrir le plan dans le planner et l'enregistrer pour
    qu'il détecte la pièce (type « room », sans nom), puis kz_open et kz_set_room.
    Types : bedroom, livingdiningRoom, kitchen, bathRoom, wc, livingRoom, diningRoom, entrance, cupboard,
    dressing, laundry, storage, bearing, corridor, office, showerRoom, playRoom, otherHabitable, balcony,
    terraceannex, garage, basement, cellar, attic, loggia, veranda, technicalArea, otherAnnex, garden,
    terraceext, driveway, carport, parking."""
    return {"id": _run(_plan().set_room, room, type=type, name=name)}


@mcp.tool
def kz_set_material(target: str, material_id: str) -> dict:
    """Applique un revêtement (material-…).
    target :
    - "floor:<pièce>" : sol de la pièce (carrelage, parquet…) ;
    - "ceiling:<pièce>" : plafond de la pièce (peinture), visible seulement en vue 3D ;
    - "wall:<pièce>" : toutes les faces de mur tournées vers la pièce (peinture, papier peint, faïence) ;
    - "wall:<pièce>:<arête>" : un seul mur, index d'arête de kz_room_geometry (mur d'accent) ;
    - "ground" : terrain autour de la maison (gazon)."""
    return _run(_plan().set_material, target, material_id)


@mcp.tool
def kz_add_pool(
    points: list[list[float]], height: float = 100, water_depth: float = 95, coping_thickness: float = 30
) -> dict:
    """Ajoute une piscine enterrée de contour `points` ([[x, y], …], cm)."""
    return {
        "id": _run(
            _plan().add_pool,
            points,
            height=height,
            water_depth=water_depth,
            coping_thickness=coping_thickness,
        )
    }


@mcp.tool
def kz_move(object_id: str, dx: float = 0, dy: float = 0, force: bool = False) -> dict:
    """Décale un objet posé de dx, dy cm (coordonnées du plan), avec les objets posés dessus. Refusé en
    cas de collision, de débattement de porte ou de fenêtre masquée, sauf force=True (tapis, retouches)."""
    return _run(_plan().move, object_id, dx, dy, force)


@mcp.tool
def kz_remove(object_id: str) -> dict:
    """Supprime un objet (modèle, ouverture, mur avec ses ouvertures, pièce, piscine…)."""
    return {"removed": _run(_plan().remove, object_id)}


@mcp.tool
def kz_get(object_id: str) -> dict:
    """JSON brut d'un objet du plan (débogage)."""
    return _run(_plan().get, object_id)


USAGE = """kazaplan-mcp            lance le serveur MCP (stdio)
kazaplan-mcp catalog    télécharge le catalogue et construit l'index (mise à jour)"""


def main():
    args = sys.argv[1:]
    if args == ["catalog"]:
        catalog.ensure(force=True)
    elif not args:
        catalog.ensure_in_background()
        mcp.run()
    else:
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
