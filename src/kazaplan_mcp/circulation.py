"""Contrôles de circulation d'une pièce : dégagements autour des meubles et chemins entre ses ouvertures.

Cotes (Côté Maison, « Les règles de circulation pour une maison agréable à vivre ») : 60 cm entre canapé
et table basse, 110 cm autour d'une table à manger, 90 cm devant un îlot ou un meuble de cuisine,
passages de 60 cm au minimum et 90 cm pour être à l'aise ; rayon.design : 75 cm devant une armoire.
"""

import math
import re

from . import catalog
from . import geometry as g
from .plan import Plan

CELL = 5
MAX_REACH = 300
REACH_STEP = 0.5
OBSTACLE_MAX_ELEVATION = 40
FLAT_MAX_H = 2
PATH_MIN = 60
PATH_COMFORT = 90
SAMPLE_SPREAD = 0.6
TABLE_REACH = 50

CHAIRS = {"M_CHAISES", "B_CHAISES"}
BEDS = {"CH_LITS", "ENF_LITS"}
WARDROBES = {"M_ARMOIRES", "D_DRESSING_OUVERTS"}
STORAGE = {"M_BUFFETS", "ENF_MEUBLES"}
KITCHEN = {"C_MEUBLE_BAS", "C_COLONNE", "C_ELECTROMENAGER"}
DOUBLE_BED_MIN_W = 130
DINING_MIN_H = 65
DINING_MIN_DEPTH = 60
ISLAND_MIN_H = 85
SEAT_LABEL = re.compile(r"^(chaise|tabouret|banc)", re.I)


def _item(o):
    for cid in (o.get("originCatalogId"), o.get("catalogId")):
        if cid and (it := catalog.get(cid)):
            return it
    return {}


def _menus(item) -> set:
    menus = set(item.get("menuCodes") or [])
    # Certains sièges n'ont aucun menu au catalogue (tabouret de bar model-1275).
    if SEAT_LABEL.match(item.get("label") or ""):
        menus.add("M_CHAISES")
    return menus


def _is_dining(menus, fp):
    return "M_TABLES" in menus and fp["h"] >= DINING_MIN_H and min(fp["w"], fp["d"]) >= DINING_MIN_DEPTH


def _rules(menus, fp, at_table) -> list[tuple[str, int, set]]:
    """(côté, cote minimale, menus des objets ignorés comme obstacles) pour un meuble."""
    if menus & CHAIRS:
        return [("derrière", 75, set())] if at_table else []
    if "M_CANAPES" in menus:
        return [("devant", 60, set())]
    if menus & BEDS:
        rules = [("devant", 60, set())]
        # Lit double tête au mur : large et plus long que large (pas un lit superposé posé en long).
        if fp["w"] >= DOUBLE_BED_MIN_W and fp["d"] > fp["w"]:
            rules += [("gauche", 60, {"CH_MEUBLE"}), ("droite", 60, {"CH_MEUBLE"})]
        return rules
    if menus & KITCHEN:
        return [("devant", 90, KITCHEN)]
    # rayon.design : 75 cm devant une armoire à portes coulissantes, 75 + largeur d'un vantail si battantes.
    if menus & WARDROBES:
        return [("devant", 75, set())]
    if menus & STORAGE:
        return [("devant", 60, set())]
    if _is_dining(menus, fp):
        # Table haute (îlot, mange-debout) : 90 autour comme un îlot ; table à manger : 110.
        minimum = 90 if fp["h"] >= ISLAND_MIN_H else 110
        return [(side, minimum, CHAIRS) for side in ("devant", "derrière", "gauche", "droite")]
    return []


def _face(fp, side):
    """Points d'échantillonnage sur une face et direction sortante. Largeur suivant θ, avant vers θ + 90°."""
    c, w, d, t = fp["center"], fp["w"], fp["d"], fp["theta"]
    u = (math.cos(t), math.sin(t))
    f = (-u[1], u[0])
    normal, half, along, span = {
        "devant": (f, d / 2, u, w / 2),
        "derrière": ((-f[0], -f[1]), d / 2, u, w / 2),
        "droite": (u, w / 2, f, d / 2),
        "gauche": ((-u[0], -u[1]), w / 2, f, d / 2),
    }[side]
    base = (c[0] + normal[0] * half, c[1] + normal[1] * half)
    pts = [
        (base[0] + along[0] * k * span, base[1] + along[1] * k * span)
        for k in (-SAMPLE_SPREAD, 0, SAMPLE_SPREAD)
    ]
    return pts, normal


class _Space:
    def __init__(self, plan: Plan):
        self.rooms = [plan.room_poly(r) for r in plan.of_type("wall.room")]
        self.walls = [poly for _, poly in plan._wall_polys()]
        self.objects = []
        for o in plan.of_type("model.model-structure"):
            fp = plan.footprint(o)
            if fp["h"] > FLAT_MAX_H and fp["y0"] < OBSTACLE_MAX_ELEVATION:
                menus = _menus(_item(o))
                self.objects.append((o["id"], menus, fp["poly"], _bbox(fp["poly"]), _is_dining(menus, fp)))

    def blocked(self, p, skip=(), ignore_menus=frozenset()):
        if not any(g.point_in_poly(p, r) for r in self.rooms):
            return True
        if any(g.point_in_poly(p, w) for w in self.walls):
            return True
        for oid, menus, poly, (x0, y0, x1, y1), _ in self.objects:
            if oid in skip or (menus & ignore_menus):
                continue
            if x0 <= p[0] <= x1 and y0 <= p[1] <= y1 and g.point_in_poly(p, poly):
                return True
        return False

    def faces_table(self, fp, skip):
        pts, normal = _face(fp, "devant")
        for oid, _, poly, _, dining in self.objects:
            if dining and oid not in skip:
                for p in pts:
                    for k in range(0, TABLE_REACH + 1, CELL):
                        if g.point_in_poly((p[0] + normal[0] * k, p[1] + normal[1] * k), poly):
                            return True
        return False

    def reach(self, p, direction, skip, ignore_menus):
        for i in range(1, int(MAX_REACH / REACH_STEP) + 1):
            d = i * REACH_STEP
            if self.blocked((p[0] + direction[0] * d, p[1] + direction[1] * d), skip, ignore_menus):
                return round(d - REACH_STEP / 2)
        return MAX_REACH


def _bbox(poly):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def clearances(plan: Plan, room: dict, space: _Space) -> list[dict]:
    poly = plan.room_poly(room)
    out = []
    for o in plan.of_type("model.model-structure"):
        fp = plan.footprint(o)
        if (
            fp["h"] <= FLAT_MAX_H
            or fp["y0"] >= OBSTACLE_MAX_ELEVATION
            or not g.point_in_poly(fp["center"], poly)
        ):
            continue
        item = _item(o)
        at_table = space.faces_table(fp, {o["id"]})
        for side, minimum, ignore in _rules(_menus(item), fp, at_table):
            pts, normal = _face(fp, side)
            free = min(space.reach(p, normal, {o["id"]}, frozenset(ignore)) for p in pts)
            out.append(
                {
                    "id": o["id"],
                    "label": item.get("label") or o.get("catalogId"),
                    "side": side,
                    "free_cm": free,
                    "min_cm": minimum,
                    "ok": free >= minimum,
                }
            )
    return out


def _portals(geo, inset):
    """Ouvertures praticables (portes, portes-fenêtres, arêtes sans mur) : points juste à l'intérieur."""
    out = []
    for e in geo["edges"]:
        a, b, n = e["from"], e["to"], e["inwardNormal"]
        length = e["length"] or 1
        u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        spans = []
        if (e.get("invisible") or not e["wallId"]) and length >= PATH_MIN:
            spans.append(("passage ouvert", None, 0, length))
        for op in e["openings"]:
            if op["kind"] == "door":
                spans.append(("porte", op["id"], op["from"], op["to"]))
            elif op["elevation"] <= CELL:
                spans.append(("porte-fenêtre", op["id"], op["from"], op["to"]))
        for kind, oid, t0, t1 in spans:
            mid = (t0 + t1) / 2
            ts = [mid + k for k in range(int(t0 - mid), int(t1 - mid) + 1, CELL)] or [mid]
            pts = [(a[0] + u[0] * t + n[0] * inset, a[1] + u[1] * t + n[1] * inset) for t in ts]
            out.append({"kind": kind, "id": oid, "edge": e["index"], "points": pts})
    out.sort(key=lambda p: p["kind"] != "porte")
    return out


def _distance_grid(space, box):
    x0, y0, x1, y1 = box
    cols, rows = int((x1 - x0) // CELL) + 1, int((y1 - y0) // CELL) + 1
    inf = float("inf")
    dist = [
        [0.0 if space.blocked((x0 + (c + 0.5) * CELL, y0 + (r + 0.5) * CELL)) else inf for c in range(cols)]
        for r in range(rows)
    ]
    diag = CELL * math.sqrt(2)
    # Transformée de distance en deux passes (chanfrein 5 / 7,07 cm).
    for r in range(rows):
        for c in range(cols):
            v = dist[r][c]
            if r:
                v = min(v, dist[r - 1][c] + CELL)
                if c:
                    v = min(v, dist[r - 1][c - 1] + diag)
                if c + 1 < cols:
                    v = min(v, dist[r - 1][c + 1] + diag)
            if c:
                v = min(v, dist[r][c - 1] + CELL)
            dist[r][c] = v
    for r in range(rows - 1, -1, -1):
        for c in range(cols - 1, -1, -1):
            v = dist[r][c]
            if r + 1 < rows:
                v = min(v, dist[r + 1][c] + CELL)
                if c + 1 < cols:
                    v = min(v, dist[r + 1][c + 1] + diag)
                if c:
                    v = min(v, dist[r + 1][c - 1] + diag)
            if c + 1 < cols:
                v = min(v, dist[r][c + 1] + CELL)
            dist[r][c] = v
    return dist, x0, y0, cols, rows


def paths(plan: Plan, room: dict, space: _Space) -> list[dict]:
    geo = plan.room_geometry(room["id"])
    poly = plan.room_poly(room)
    bx0, by0, bx1, by1 = _bbox(poly)
    dist, x0, y0, cols, rows = _distance_grid(space, (bx0 - 20, by0 - 20, bx1 + 20, by1 + 20))

    def cell(p):
        c, r = int((p[0] - x0) // CELL), int((p[1] - y0) // CELL)
        return (r, c) if 0 <= r < rows and 0 <= c < cols else None

    results = {}
    portals = []
    for width in (PATH_MIN, PATH_COMFORT):
        radius = width / 2
        portals = _portals(geo, radius + CELL)
        if not portals:
            return []
        ok = [[dist[r][c] >= radius for c in range(cols)] for r in range(rows)]
        start = [rc for p in portals[0]["points"] if (rc := cell(p)) and ok[rc[0]][rc[1]]]
        seen = set(start)
        stack = list(start)
        while stack:
            r, c = stack.pop()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and ok[nr][nc] and (nr, nc) not in seen:
                    seen.add((nr, nc))
                    stack.append((nr, nc))
        for i, p in enumerate(portals[1:], 1):
            results.setdefault(i, {})[width] = any(cell(q) in seen for q in p["points"])

    src = portals[0]
    return [
        {
            "from": f"{src['kind']} (arête {src['edge']})",
            "to": f"{p['kind']} (arête {p['edge']})",
            "id": p["id"],
            "width60": results.get(i, {}).get(PATH_MIN, False),
            "width90": results.get(i, {}).get(PATH_COMFORT, False),
        }
        for i, p in enumerate(portals[1:], 1)
    ]


def check(plan: Plan, room: str) -> dict:
    """Dégagements autour des meubles (cotes minimales selon le type) et chemins de 60 / 90 cm entre la porte
    d'entrée de la pièce et ses autres ouvertures."""
    r = plan.room(room)
    space = _Space(plan)
    clear = clearances(plan, r, space)
    return {
        "room": plan.room_label(r),
        "clearances": clear,
        "issues": [c for c in clear if not c["ok"]],
        "paths": paths(plan, r, space),
    }
