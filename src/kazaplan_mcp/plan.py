"""Modèle d'un plan Kazaplan (JSON `wnp/project`) : lecture, géométrie, modifications.

Conventions vérifiées sur un plan réel :
- plan 2D (x, y) en cm ; position 3D = (x, hauteur, -y) ;
- ouverture : position = centre sur l'axe du mur, rotation.y = angle de l'axe du mur (a -> b) ;
- modèle : rotation.y = theta ⇒ largeur suivant theta, face avant vers theta + 90°.
"""

import copy
import math
import time
import uuid
from datetime import UTC, datetime

from . import catalog, kzp
from . import geometry as g

# Types reconnus par le planner (table interne du bundle, 2026-10).
ROOM_TYPES = {
    "bedroom": "Chambre",
    "livingdiningRoom": "Séjour / salle à manger",
    "kitchen": "Cuisine",
    "bathRoom": "Salle de bain",
    "wc": "WC",
    "livingRoom": "Salon",
    "diningRoom": "Salle à manger",
    "entrance": "Entrée",
    "cupboard": "Placard",
    "dressing": "Dressing",
    "laundry": "Buanderie",
    "storage": "Rangement",
    "bearing": "Palier",
    "corridor": "Couloir",
    "office": "Bureau",
    "showerRoom": "Salle d'eau",
    "playRoom": "Salle de jeux",
    "otherHabitable": "Autre pièce à vivre",
    "balcony": "Balcon",
    "terraceannex": "Toit-terrasse",
    "garage": "Garage",
    "basement": "Sous-sol",
    "cellar": "Cave",
    "attic": "Combles",
    "loggia": "Loggia",
    "veranda": "Véranda",
    "technicalArea": "Local technique",
    "otherAnnex": "Annexe",
    "garden": "Jardin",
    "terraceext": "Terrasse",
    "driveway": "Allée",
    "carport": "Carport",
    "parking": "Parking",
    "room": "Pièce",
}
OPENING_KINDS = {"door": "opening.door", "casement-window": "opening.casementwindow"}
DOOR_MARGIN = 5
WALL_TOL = 4
ON_TOP_TOLERANCE = 2
FLAT_MAX_H = 2
GEOMETRY_TYPES = {"wall.wall", "wall.room", "opening.door", "opening.casementwindow"}


def v2(x, y):
    return {"x": x, "y": y, "__name__": "babylon-vector2"}


def v3(x, y, z):
    return {"x": x, "y": y, "z": z, "__name__": "babylon-vector3"}


def pt(v) -> g.Pt:
    return (v["x"], v["y"])


def plan_xy(pos3) -> g.Pt:
    return (pos3["x"], -pos3["z"])


def _wrap(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def _now_ms():
    return time.time() * 1000


def is_invisible(wall: dict) -> bool:
    """Séparation invisible du planner (pièces ouvertes, limites de terrasse) : vrai wall.wall de 2 cm,
    rendu par wall.invisible-renderer, sans collision."""
    return (wall.get("wallRenderer") or {}).get("__name__") == "wall.invisible-renderer"


def _prune_pane_refs(objects: list[dict]) -> list[dict]:
    """Retire les références vers des wall.pane absents. Le planner régénère les faces d'un mur ou
    d'une pièce sans paneIds, mais plante à l'ouverture (_updateLinkedPanes) sur un id orphelin."""
    panes = {o["id"] for o in objects if o["__name__"] == "wall.pane"}
    out = []
    for o in objects:
        if o["__name__"] == "baseboard.baseboard-structure" and o.get("paneId") not in panes:
            continue
        if o["__name__"] == "wall.wall":
            o["paneIds"] = {k: v for k, v in (o.get("paneIds") or {}).items() if k in panes}
        elif o["__name__"] == "wall.room":
            o["paneIds"] = [p for p in o.get("paneIds") or [] if p in panes]
        out.append(o)
    return out


class PlanError(ValueError):
    pass


class Plan:
    def __init__(self, metadata: dict, project: dict, blobs: dict | None = None):
        self.metadata = metadata
        self.project = project
        self.blobs = blobs or {}
        self.geometry_dirty = False
        layers = project["layers"]
        hist = (layers.get("floorHistory") or [{}])[0]
        self.floor_id = hist.get("currentFloorId") or layers["floors"][0]["id"]
        self.floor = next(f for f in layers["floors"] if f["id"] == self.floor_id)
        self.partner_meta = next(
            (o.get("metadata") for o in self.objects if o.get("metadata")),
            {"addedAtPartner": "7"},
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "Plan":
        _, metadata, project, blobs = kzp.load(data)
        return cls(metadata, project, blobs)

    def to_bytes(self) -> bytes:
        project = copy.deepcopy(self.project)
        # Ne jamais supprimer les wall.pane : le planner ne les régénère que pour des murs sans paneIds
        # (murs neufs) et plante à l'ouverture (_updateLinkedPanes) si les murs existants n'en ont plus.
        floor = _prune_pane_refs(project["layers"][self.floor_id])
        for o in floor:
            o.pop("initParams", None)
            o.pop("trackerData", None)
        project["layers"][self.floor_id] = floor
        metadata = dict(self.metadata)
        metadata["lastUpdate"] = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        data = kzp.dump(metadata, project, self.blobs)
        kzp.load(data)
        return data

    # ---- accès -------------------------------------------------------------

    @property
    def objects(self) -> list[dict]:
        return self.project["layers"][self.floor_id]

    def of_type(self, *names) -> list[dict]:
        return [o for o in self.objects if o["__name__"] in names]

    def get(self, obj_id: str) -> dict:
        for o in self.objects:
            if o["id"] == obj_id:
                return o
        raise PlanError(f"Objet introuvable : {obj_id}")

    def room_label(self, room: dict) -> str:
        if room.get("customName"):
            return room["customName"]
        base = ROOM_TYPES.get(room["type"], room["type"])
        same = [r for r in self.of_type("wall.room") if not r.get("customName") and r["type"] == room["type"]]
        return base if len(same) < 2 else f"{base} {same.index(room) + 1}"

    def room(self, ref: str) -> dict:
        rooms = self.of_type("wall.room")
        key = catalog.norm(ref)
        for r in rooms:
            if r["id"] == ref:
                return r
        exact = [r for r in rooms if catalog.norm(self.room_label(r)) == key]
        if len(exact) == 1:
            return exact[0]
        loose = [
            r
            for r in rooms
            if key in catalog.norm(self.room_label(r))
            or key == catalog.norm(r["type"])
            or key in catalog.norm(ROOM_TYPES.get(r["type"], ""))
        ]
        if len(loose) == 1:
            return loose[0]
        names = [self.room_label(r) for r in (loose or rooms)]
        raise PlanError(f"Pièce « {ref} » {'ambiguë' if loose else 'introuvable'} : {names}")

    @staticmethod
    def room_poly(room: dict) -> list[g.Pt]:
        return [pt(p) for p in room["path"][0]]

    def room_at(self, p: g.Pt) -> dict | None:
        for r in self.of_type("wall.room"):
            if g.point_in_poly(p, self.room_poly(r)):
                return r
        return None

    # ---- objets posés ------------------------------------------------------

    def footprint(self, o: dict) -> dict:
        dims = o.get("boundings", {}).get("dimensions") or {}
        sc = o.get("meshScaling") or {"x": 1, "y": 1, "z": 1}
        w = (dims.get("width") or 0) * sc["x"]
        d = (dims.get("depth") or 0) * sc["z"]
        h = (dims.get("height") or 0) * sc["y"]
        c = plan_xy(o["position"])
        theta = o["rotation"]["y"]
        return {
            "center": c,
            "w": w,
            "d": d,
            "h": h,
            "theta": theta,
            "y0": o["position"]["y"],
            "poly": g.obb(c, w, d, theta),
        }

    def models(self) -> list[dict]:
        out = []
        for o in self.of_type("model.model-structure"):
            fp = self.footprint(o)
            cid = o.get("catalogId") or o.get("originCatalogId")
            item = catalog.get(cid) if cid else None
            room = self.room_at(fp["center"])
            out.append(
                {
                    "id": o["id"],
                    "catalogId": cid,
                    "label": item["label"] if item else None,
                    "room": self.room_label(room) if room else None,
                    "x": round(fp["center"][0], 1),
                    "y": round(fp["center"][1], 1),
                    "elevation": round(fp["y0"], 1),
                    "rotationDeg": round(math.degrees(fp["theta"]), 1),
                    "w": round(fp["w"], 1),
                    "d": round(fp["d"], 1),
                    "h": round(fp["h"], 1),
                }
            )
        return out

    # ---- géométrie des pièces ---------------------------------------------

    def _openings(self):
        walls = {w["id"]: w for w in self.of_type("wall.wall")}
        out = []
        for o in self.objects:
            if not o["__name__"].startswith("opening."):
                continue
            w = walls.get(o.get("parentWallId"))
            out.append(
                {
                    "id": o["id"],
                    "kind": "door" if o["__name__"] == "opening.door" else "window",
                    "center": plan_xy(o["position"]),
                    "width": o["width"],
                    "height": o["height"],
                    "elevation": o.get("elevation", 0),
                    "wallThickness": w["thickness"] if w else 20,
                    "wallId": o.get("parentWallId"),
                }
            )
        return out

    def _wall_for_edge(self, e) -> dict | None:
        best = None
        for w in self.of_type("wall.wall"):
            a, b = (pt(x["position"]) for x in w["connectionExtremities"])
            t0, d0 = g.project(a, e["a"], e["u"])
            t1, d1 = g.project(b, e["a"], e["u"])
            half = w["thickness"] / 2
            if abs(abs(d0) - half) > WALL_TOL or abs(abs(d1) - half) > WALL_TOL:
                continue
            overlap = min(max(t0, t1), e["length"]) - max(min(t0, t1), 0)
            if overlap > 1 and (best is None or overlap > best[0]):
                best = (overlap, w)
        return best[1] if best else None

    def room_geometry(self, ref: str) -> dict:
        room = self.room(ref)
        poly = self.room_poly(room)
        openings = self._openings()
        out_edges, door_zones, window_bands = [], [], []
        for e in g.edges(poly):
            ops, cuts = [], []
            for op in openings:
                t, dist = g.project(op["center"], e["a"], e["u"])
                if abs(abs(dist) - op["wallThickness"] / 2) > WALL_TOL:
                    continue
                t0, t1 = t - op["width"] / 2, t + op["width"] / 2
                if t1 <= 0 or t0 >= e["length"]:
                    continue
                ops.append(
                    {
                        "id": op["id"],
                        "kind": op["kind"],
                        "from": round(t0, 1),
                        "to": round(t1, 1),
                        "width": op["width"],
                        "height": op["height"],
                        "elevation": op["elevation"],
                    }
                )
                if op["kind"] == "door":
                    cuts.append((t0 - DOOR_MARGIN, t1 + DOOR_MARGIN))
                    door_zones.append(
                        {
                            "openingId": op["id"],
                            "poly": g.rect_on_edge(e["a"], e["u"], e["n"], t0, t1, op["width"]),
                        }
                    )
                else:
                    cuts.append((t0, t1))
                    window_bands.append(
                        {
                            "openingId": op["id"],
                            "elevation": op["elevation"],
                            "poly": g.rect_on_edge(e["a"], e["u"], e["n"], t0, t1, 5),
                        }
                    )
            wall = self._wall_for_edge(e)
            out_edges.append(
                {
                    "index": e["index"],
                    "from": [round(c, 1) for c in e["a"]],
                    "to": [round(c, 1) for c in e["b"]],
                    "length": round(e["length"], 1),
                    "inwardNormal": [round(c, 3) for c in e["n"]],
                    "wallId": wall["id"] if wall else None,
                    "wallThickness": wall["thickness"] if wall else None,
                    **({"invisible": True} if wall and is_invisible(wall) else {}),
                    "openings": sorted(ops, key=lambda o: o["from"]),
                    "free": []
                    if wall and is_invisible(wall)
                    else g.subtract_intervals((0, e["length"]), cuts),
                }
            )
        area = abs(g.signed_area(poly)) / 1e4
        occupied = sum(
            m["w"] * m["d"] / 1e4
            for m in self.models()
            if m["room"] == self.room_label(room) and m["elevation"] <= (room.get("elevation") or 0) + 1
        )
        return {
            "room": self.room_label(room),
            "id": room["id"],
            "type": room["type"],
            "area_m2": round(area, 2),
            "usable_m2": round(area - occupied, 2),
            "flooring": room.get("materials", {}).get("flooring"),
            "elevation": room.get("elevation") or 0,
            "edges": out_edges,
            "doorSwingZones": [
                {**z, "poly": [[round(c, 1) for c in p] for p in z["poly"]]} for z in door_zones
            ],
            "_windowBands": window_bands,
            "_poly": poly,
            "_room": room,
        }

    # ---- résumé ------------------------------------------------------------

    def summary(self) -> dict:
        rooms = []
        for r in self.of_type("wall.room"):
            poly = self.room_poly(r)
            xs, ys = [p[0] for p in poly], [p[1] for p in poly]
            flooring = (r.get("materials") or {}).get("flooring", "")
            mat = catalog.get(flooring.removeprefix("catalog:")) if flooring else None
            rooms.append(
                {
                    "id": r["id"],
                    "name": self.room_label(r),
                    "type": r["type"],
                    "area_m2": round(abs(g.signed_area(poly)) / 1e4, 2),
                    "bbox_cm": [round(max(xs) - min(xs)), round(max(ys) - min(ys))],
                    "flooring": (mat["label"] if mat else flooring) or None,
                }
            )
        openings = []
        for op in self._openings():
            openings.append(
                {
                    "id": op["id"],
                    "kind": op["kind"],
                    "width": op["width"],
                    "height": op["height"],
                    "elevation": op["elevation"],
                    "wallId": op["wallId"],
                    "x": round(op["center"][0], 1),
                    "y": round(op["center"][1], 1),
                }
            )
        walls = self.of_type("wall.wall")
        pools = [
            {
                "id": p["id"],
                "points": [[round(c, 1) for c in pt(v)] for v in p["points"]],
                "waterDepth": p.get("waterDepth"),
                "height": p.get("height"),
            }
            for p in self.of_type("swimming-pool.swimming-pool")
        ]
        return {
            "title": self.project.get("title"),
            "floor": {k: self.floor[k] for k in ("id", "ceilingHeight", "slabThickness")},
            "rooms": rooms,
            "walls": {"count": len(walls), "thicknesses": sorted({w["thickness"] for w in walls})},
            "openings": openings,
            "objects": self.models(),
            "pools": pools,
            "geometryDirty": self.geometry_dirty,
        }

    # ---- catalogue dans le plan -------------------------------------------

    def _touch_catalog(self, item_id: str):
        layer = self.project["layers"].setdefault("catalog", [])
        if not layer:
            layer.append(
                {
                    "__name__": "catalog-diff",
                    "id": str(uuid.uuid4()),
                    "metadata": dict(self.partner_meta),
                    "itemDiff": {},
                }
            )
        now = _now_ms()
        diff = layer[0].setdefault("itemDiff", {})
        entry = diff.setdefault(item_id, {})
        entry["lastUsed"] = now
        if item_id.startswith("material-"):
            tr = entry.setdefault("trackerData", {}).setdefault(f"catalog:{item_id}", {"firstUsed": now})
            tr["lastUsed"] = now

    def _new(self, obj: dict) -> dict:
        obj["id"] = str(uuid.uuid4())
        obj["metadata"] = dict(self.partner_meta)
        return obj

    # ---- placement ---------------------------------------------------------

    def _wall_polys(self):
        for w in self.of_type("wall.wall"):
            if is_invisible(w):
                continue
            a, b = (pt(x["position"]) for x in w["connectionExtremities"])
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            if length < 1e-6:
                continue
            u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
            n = (-u[1], u[0])
            half = w["thickness"] / 2
            start = (a[0] - n[0] * half, a[1] - n[1] * half)
            yield w, g.rect_on_edge(start, u, n, 0, length, w["thickness"])

    def check_footprint(self, poly, y0, h, geo, ignore_ids=()) -> list[str]:
        issues = []
        if geo is None:
            for w, wp in self._wall_polys():
                if g.polys_overlap(poly, wp):
                    issues.append(f"traverse le mur {w['id']}")
            return issues + self._model_overlaps(poly, y0, h, ignore_ids)
        shrink = []
        cx = sum(p[0] for p in poly) / 4
        cy = sum(p[1] for p in poly) / 4
        for p in poly:
            dx, dy = p[0] - cx, p[1] - cy
            n = math.hypot(dx, dy) or 1
            shrink.append((p[0] - dx / n, p[1] - dy / n))
        if not all(g.point_in_poly(p, geo["_poly"]) for p in shrink):
            issues.append("dépasse des murs de la pièce")
        floor_y = geo["elevation"]
        if y0 < floor_y + 60:
            for z in geo["doorSwingZones"]:
                if g.polys_overlap(poly, [tuple(p) for p in z["poly"]]):
                    issues.append(f"empiète sur le débattement de la porte {z['openingId']}")
        for band in geo["_windowBands"]:
            if y0 + h > floor_y + band["elevation"] + 1 and g.polys_overlap(poly, band["poly"]):
                issues.append(f"masque la fenêtre {band['openingId']} (allège {band['elevation']} cm)")
        return issues + self._model_overlaps(poly, y0, h, ignore_ids)

    @staticmethod
    def _no_collision(catalog_id: str | None) -> bool:
        item = catalog.get(catalog_id) if catalog_id else None
        return bool(item) and "NO_COLLISION" in item.get("magnetism", [])

    def _model_overlaps(self, poly, y0, h, ignore_ids) -> list[str]:
        # Un tapis n'est un obstacle pour rien, et rien ne l'est pour lui.
        if h <= FLAT_MAX_H:
            return []
        issues = []
        for o in self.of_type("model.model-structure"):
            if o["id"] in ignore_ids or self._no_collision(o.get("catalogId") or o.get("originCatalogId")):
                continue
            fp = self.footprint(o)
            if fp["h"] <= FLAT_MAX_H:
                continue
            if fp["y0"] >= y0 + h or y0 >= fp["y0"] + fp["h"]:
                continue
            if g.polys_overlap(poly, fp["poly"]):
                cid = o.get("catalogId") or o.get("originCatalogId")
                issues.append(f"chevauche l'objet {o['id']} ({cid})")
        return issues

    def place(
        self,
        model_id: str,
        room: str | None,
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
        item = catalog.get(model_id)
        if not item or item["kind"] != "model":
            raise PlanError(f"Modèle inconnu : {model_id}")
        tpl = catalog.templates().get(model_id)
        if not tpl:
            raise PlanError(f"{model_id} ({item['type']}) n'est pas un prefab plaçable")
        support = None
        if on_top_of:
            support = self.footprint(self.get(on_top_of))
            if x is None or y is None:
                x, y = support["center"]
            if room is None:
                found = self.room_at(support["center"])
                room = found["id"] if found else None
        if room is None and (x is None or y is None):
            raise PlanError("Hors pièce (extérieur) : x et y obligatoires")
        geo = self.room_geometry(room) if room else None
        w0, d0, h0 = item["w"] or 0, item["d"] or 0, item["h"] or 0
        resized = any(v is not None for v in (width, depth, height))
        if resized and len(tpl) > 1:
            raise PlanError(f"{model_id} est composé de {len(tpl)} éléments : redimensionnement non supporté")
        w, d, h = width or w0, depth or d0, height or h0
        scale = (w / w0 if w0 else 1, h / h0 if h0 else 1, d / d0 if d0 else 1)
        base = geo["elevation"] if geo else self._ground_height()
        if elevation is not None:
            y0 = base + elevation
        elif support is not None:
            y0 = support["y0"] + support["h"]
        else:
            y0 = base + (item.get("elevation") or 0)
        extra = math.radians(rotation or 0)

        def at_edge(e, t_center):
            n = e["inwardNormal"]
            a = e["from"]
            u = ((e["to"][0] - a[0]) / e["length"], (e["to"][1] - a[1]) / e["length"])
            theta = _wrap(math.atan2(n[1], n[0]) - math.pi / 2 + extra)
            depth = d if abs(math.sin(extra)) < 0.5 else w
            c = (
                a[0] + u[0] * t_center + n[0] * (depth / 2 + gap),
                a[1] + u[1] * t_center + n[1] * (depth / 2 + gap),
            )
            return c, theta

        def span(theta_extra):
            return w if abs(math.sin(theta_extra)) < 0.5 else d

        candidates = []
        if x is not None and y is not None:
            candidates.append(((x, y), extra))
        elif center:
            c = g.centroid(geo["_poly"])
            candidates.append((c, extra))
        elif under_opening:
            for e in geo["edges"]:
                op = next((o for o in e["openings"] if o["id"] == under_opening), None)
                if op:
                    candidates.append(at_edge(e, (op["from"] + op["to"]) / 2))
                    break
            else:
                raise PlanError(f"Ouverture {under_opening} absente des murs de {geo['room']}")
        else:
            edges = geo["edges"]
            if against_wall is not None:
                edges = [e for e in edges if e["index"] == against_wall]
                if not edges:
                    raise PlanError(f"Arête {against_wall} absente de {geo['room']}")
            else:
                edges = sorted((e for e in edges if e["wallId"]), key=lambda e: -e["length"])
            need = span(extra)
            for e in edges:
                if offset is not None:
                    candidates.append(at_edge(e, offset + need / 2))
                    continue
                for f0, f1 in sorted(e["free"], key=lambda f: f[0] - f[1]):
                    if f1 - f0 < need:
                        continue
                    mid = (f0 + f1) / 2
                    steps = [mid] + [
                        t
                        for k in range(1, int((f1 - f0 - need) / 10) + 1)
                        for t in (mid - 10 * k, mid + 10 * k)
                        if f0 + need / 2 <= t <= f1 - need / 2
                    ]
                    candidates.extend(at_edge(e, t) for t in steps)
            if not candidates:
                raise PlanError(f"Aucun segment de mur libre de {need:.0f} cm dans {geo['room']}")

        free_pass = self._no_collision(model_id)
        best = None
        for c, theta in candidates:
            poly = g.obb(c, w, d, theta)
            issues = self.check_footprint(poly, y0, h, geo)
            if free_pass:
                issues = [i for i in issues if not i.startswith("chevauche")]
            if on_top_of:
                issues = [i for i in issues if on_top_of not in i]
            if not issues:
                best = (c, theta, [])
                break
            if best is None:
                best = (c, theta, issues)
        c, theta, issues = best
        if issues and not force:
            raise PlanError("Placement refusé : " + "; ".join(issues) + " (force=True pour passer outre)")

        cos, sin = math.cos(theta), math.sin(theta)
        # Les y des gabarits sont des hauteurs absolues d'édition (-20, -40…) : on les ramène au sol.
        base_y = min(s["position"]["y"] for s in tpl)
        ids = []
        for s in tpl:
            obj = copy.deepcopy(s)
            obj.pop("initParams", None)
            obj.pop("trackerData", None)
            sx, sy, sz = obj["position"]["x"], obj["position"]["y"], obj["position"]["z"]
            if resized:
                obj["meshScaling"] = v3(*scale)
            obj["position"] = v3(c[0] + sx * cos + sz * sin, y0 + sy - base_y, -c[1] - sx * sin + sz * cos)
            r = obj.get("rotation") or v3(0, 0, 0)
            obj["rotation"] = v3(r["x"], r["y"] + theta, r["z"])
            obj.setdefault("catalogId", obj.get("originCatalogId", model_id))
            self._new(obj)
            self.objects.append(obj)
            self._touch_catalog(obj["catalogId"])
            ids.append(obj["id"])
        self._touch_catalog(model_id)
        return {
            "ids": ids,
            "model": model_id,
            "label": item["label"],
            "room": geo["room"] if geo else None,
            "x": round(c[0], 1),
            "y": round(c[1], 1),
            "rotationDeg": round(math.degrees(theta), 1),
            "elevation": round(y0 - base, 1),
            "w": w,
            "d": d,
            "h": h,
            "warnings": issues,
        }

    def _ground_height(self) -> float:
        ground = self.project["layers"].get("ground") or [{}]
        return ground[0].get("referenceHeight", 0)

    # ---- construction ------------------------------------------------------

    def add_walls(
        self,
        points: list[list[float]],
        thickness: float = 20,
        height: float | None = None,
        closed: bool = False,
    ) -> list[str]:
        if len(points) < 2:
            raise PlanError("Au moins 2 points")
        height = height or self.floor["ceilingHeight"]
        points = [list(p) for p in points]
        ids_new = [str(uuid.uuid4()) for _ in range(len(points) - (0 if closed else 1))]
        joins: dict[int, dict] = {}
        if not closed:
            for idx, other in ((0, 1), (len(points) - 1, len(points) - 2)):
                own = ids_new[0] if idx == 0 else ids_new[-1]
                j = self._attach_end(points[idx], points[other], own)
                if j:
                    points[idx] = list(j.pop("snapped"))
                    joins[idx] = j
        ends = points[1:] + ([points[0]] if closed else [])
        segs = list(zip(points[: len(ends)], ends, strict=True))
        ids = ids_new
        n = len(segs)
        for i, (a, b) in enumerate(segs):
            prev = ids[i - 1] if (closed or i > 0) and n > 1 else None
            nxt = ids[(i + 1) % n] if (closed or i < n - 1) and n > 1 else None
            start_j = joins.get(0) if i == 0 else None
            end_j = joins.get(len(points) - 1) if i == n - 1 else None
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < 1:
                raise PlanError(f"Segment {i} trop court")
            wall = {
                "__name__": "wall.wall",
                "id": ids[i],
                "metadata": dict(self.partner_meta),
                "thickness": thickness,
                "serializedHeight": height,
                "stickToSlab": True,
                "measureSideToKeep": 1,
                "storedVector": v2(dx / length, dy / length),
                "paneIds": {},
                "wallRenderer": {"__name__": "wall.wall-renderer", "id": str(uuid.uuid4())},
                "fusionable": True,
                "connectionExtremities": [
                    start_j
                    or {
                        "position": v2(*a),
                        "wallId": prev,
                        "targetEdgeIndex": -1,
                        "strong": prev is not None,
                    },
                    end_j
                    or {"position": v2(*b), "wallId": nxt, "targetEdgeIndex": -1, "strong": nxt is not None},
                ],
                "materials": {},
                "baseMaterials": {},
                "collidingEnabled": False,
                "colliderEnabled": True,
                "editable": True,
            }
            self.objects.append(wall)
        self.geometry_dirty = True
        return ids

    def _attach_end(self, p, toward, own_id: str) -> dict | None:
        """Raccorde l'extrémité libre `p` d'une nouvelle chaîne à un mur existant, comme le planner :
        - sur une extrémité libre d'un mur : coin (strong, targetEdgeIndex -1, lien dans les deux sens) ;
        - sur le flanc d'un mur : T, extrémité posée sur la face, targetEdgeIndex 1 (côté gauche de a→b,
          normale (-u.y, u.x)) ou 3 (côté droit), strong False. Relevé sur 21 jonctions d'un plan réel."""
        best = None
        for w in self.of_type("wall.wall"):
            exts = w["connectionExtremities"]
            a, b = (pt(x["position"]) for x in exts)
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            if length < 1e-6:
                continue
            half = w["thickness"] / 2
            for k, q in enumerate((a, b)):
                dist = math.hypot(p[0] - q[0], p[1] - q[1])
                if dist <= half + WALL_TOL and not exts[k].get("wallId") and (best is None or dist < best[0]):
                    best = (dist, "corner", w, k, q)
            u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
            nrm = (-u[1], u[0])
            t = (p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1]
            s = (p[0] - a[0]) * nrm[0] + (p[1] - a[1]) * nrm[1]
            if half < t < length - half and abs(s) <= half + WALL_TOL:
                if abs(s) <= 1:
                    s = (toward[0] - a[0]) * nrm[0] + (toward[1] - a[1]) * nrm[1]
                side = 1 if s > 0 else -1
                q = (a[0] + u[0] * t + nrm[0] * half * side, a[1] + u[1] * t + nrm[1] * half * side)
                dist = abs(abs(s) - half) if abs(s) > 1 else 0.0
                if best is None or dist < best[0]:
                    best = (dist, "tee", w, 1 if side > 0 else 3, q)
        if best is None:
            return None
        _, kind, w, k, q = best
        if kind == "corner":
            w["connectionExtremities"][k].update(wallId=own_id, targetEdgeIndex=-1, strong=True)
            return {
                "snapped": q,
                "position": v2(*q),
                "wallId": w["id"],
                "targetEdgeIndex": -1,
                "strong": True,
            }
        return {"snapped": q, "position": v2(*q), "wallId": w["id"], "targetEdgeIndex": k, "strong": False}

    def add_opening(
        self,
        wall_id: str,
        kind: str = "door",
        offset: float | None = None,
        width: float | None = None,
        height: float | None = None,
        elevation: float | None = None,
        nb_casement: int | None = None,
        side: bool = True,
        hinge: bool = True,
    ) -> str:
        if kind not in OPENING_KINDS:
            raise PlanError(f"Type d'ouverture supporté : {list(OPENING_KINDS)}")
        wall = self.get(wall_id)
        if wall["__name__"] != "wall.wall":
            raise PlanError(f"{wall_id} n'est pas un mur")
        a, b = (pt(x["position"]) for x in wall["connectionExtremities"])
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        is_door = kind == "door"
        width = width or (90 if is_door else 100)
        height = height or (215 if is_door else 135)
        elevation = elevation if elevation is not None else (0 if is_door else 95)
        t = offset + width / 2 if offset is not None else length / 2
        if t - width / 2 < 0 or t + width / 2 > length:
            raise PlanError(f"L'ouverture ({width} cm) sort du mur ({length:.0f} cm)")
        for op in self._openings():
            if op["wallId"] != wall_id:
                continue
            ot, _ = g.project(op["center"], a, u)
            if abs(ot - t) < (op["width"] + width) / 2:
                raise PlanError(f"Chevauche l'ouverture {op['id']}")
        c = (a[0] + u[0] * t, a[1] + u[1] * t)
        obj = {
            "__name__": OPENING_KINDS[kind],
            "width": width,
            "height": height,
            "elevation": elevation,
            "position": v3(c[0], elevation, -c[1]),
            "rotation": v3(0, math.atan2(u[1], u[0]), 0),
            "symmetryX": False,
            "symmetryZ": False,
            "originCatalogId": kind,
            "owned": [],
            "replaceInfo": {"catalogId": kind},
            "collidingEnabled": False,
            "colliderEnabled": False,
            "maxDepthOffsetBetweenStructures": 61,
            "frontOffsetFromPosition": 55,
            "backOffsetFromPosition": 55,
            "materials": {},
            "baseMaterials": {
                "in": "static:component/opening/greyPaint",
                "out": "static:component/opening/greyPaint",
                "hinge": "static:component/opening/metal",
                "handle": "static:component/opening/metal",
                **(
                    {}
                    if is_door
                    else {
                        "glass-in": "static:component/opening/glass",
                        "glass-out": "static:component/opening/glass",
                    }
                ),
            },
            "side": side,
            "hinge": hinge,
            "openingDepth": 0.5,
            "sashThickness": 5,
            "frameThickness": 7 if is_door else 5,
            "nbCasement": nb_casement or (1 if is_door else 2),
            "parentWallId": wall_id,
            "editable": True,
            "outerFrameThickness": 0,
            **({"sillThickness": 0} if is_door else {"sashDepth": 6}),
        }
        self._new(obj)
        self.objects.append(obj)
        self.geometry_dirty = True
        return obj["id"]

    def set_room(self, ref: str, type: str | None = None, name: str | None = None) -> str:
        """Renomme / retype une pièce existante. Les pièces ne sont jamais créées dans le fichier : une
        wall.room écrite par le MCP n'a pas de wall.pane, et le planner plante à l'ouverture
        (_updateLinkedPanes) puis ne peut plus enregistrer. Le planner détecte lui-même les pièces fermées
        par des murs (type « room ») à la prochaine ouverture + enregistrement."""
        room = self.room(ref)
        if type is not None:
            if type not in ROOM_TYPES:
                raise PlanError(f"Type de pièce inconnu : {type}. Types : {sorted(ROOM_TYPES)}")
            room["type"] = type
        if name is not None:
            room["customName"] = name or None
        return room["id"]

    def room_panes(self, room: dict, edge: int | None = None) -> list[dict]:
        """Faces de mur (wall.pane) tournées vers la pièce, éventuellement limitées à une arête."""
        hidden = {w["id"] for w in self.of_type("wall.wall") if is_invisible(w)}
        panes = [
            p
            for p in self.of_type("wall.pane")
            if (p.get("roomInfo") or {}).get("id") == room["id"]
            and (p.get("wallInfo") or {}).get("id") not in hidden
        ]
        if edge is None:
            return panes
        geo = self.room_geometry(room["id"])
        e = next((e for e in geo["edges"] if e["index"] == edge), None)
        if e is None:
            raise PlanError(f"Arête {edge} absente de {geo['room']}")
        if not e["wallId"] or e.get("invisible"):
            raise PlanError(f"L'arête {edge} de {geo['room']} n'a pas de mur visible à revêtir")
        return [p for p in panes if (p.get("wallInfo") or {}).get("id") == e["wallId"]]

    def set_material(self, target: str, material_id: str) -> dict:
        """target : « floor:<pièce> », « ceiling:<pièce> », « wall:<pièce> » (tous les murs),
        « wall:<pièce>:<arête> » (un mur, index de kz_room_geometry) ou « ground » (terrain autour
        de la maison)."""
        item = catalog.get(material_id)
        if not item or item["kind"] != "material":
            raise PlanError(f"Matériau inconnu : {material_id}")
        kind, _, ref = target.partition(":")
        usage = item.get("usage", [])
        ref_mat = f"catalog:{material_id}"
        if kind == "floor":
            room = self.room(ref)
            room.setdefault("materials", {})["flooring"] = ref_mat
            self._touch_catalog(material_id)
            warn = [] if "floor" in usage else ["matériau non classé « sol » dans le catalogue"]
            return {"room": self.room_label(room), "flooring": material_id, "warnings": warn}
        if kind == "ceiling":
            room = self.room(ref)
            if room.get("ceiling") is False:
                raise PlanError(f"{self.room_label(room)} est une pièce sans plafond")
            # Clé lue par le planner : room.getMaterial("ceil") (pane-structure, bundle du 2026-10-15).
            room.setdefault("materials", {})["ceil"] = ref_mat
            self._touch_catalog(material_id)
            warn = [] if "wall" in usage else ["matériau non classé « mur » dans le catalogue"]
            return {"room": self.room_label(room), "ceiling": material_id, "warnings": warn}
        if kind == "wall":
            name, _, edge = ref.rpartition(":")
            if not (name and edge.lstrip("-").isdigit()):
                name, edge = ref, None
            room = self.room(name)
            panes = self.room_panes(room, int(edge) if edge is not None else None)
            if not panes:
                raise PlanError(
                    f"Aucune face de mur pour {self.room_label(room)} : ouvrir puis enregistrer le plan "
                    "dans le planner pour qu'il calcule les faces des murs neufs"
                )
            # Clé relevée sur un mur peint dans le planner (2026-10-14) : materials["wall.pane"].
            for p in panes:
                p.setdefault("materials", {})["wall.pane"] = ref_mat
            self._touch_catalog(material_id)
            warn = [] if "wall" in usage else ["matériau non classé « mur » dans le catalogue"]
            return {"room": self.room_label(room), "panes": len(panes), "wall": material_id, "warnings": warn}
        if kind == "ground":
            ground = self.project["layers"].get("ground")
            if not ground:
                raise PlanError("Le plan n'a pas de calque « ground »")
            # Clé « ground » tirée des defaultMaterials du planner ({earth, ground}), à valider au rendu.
            ground[0].setdefault("materials", {})["ground"] = ref_mat
            self._touch_catalog(material_id)
            warn = [] if "floor" in usage else ["matériau non classé « sol » dans le catalogue"]
            return {"ground": material_id, "warnings": warn}
        raise PlanError(
            "Cible : « floor:<pièce> », « ceiling:<pièce> », « wall:<pièce> », « wall:<pièce>:<arête> » "
            "ou « ground »"
        )

    def add_pool(
        self,
        points: list[list[float]],
        height: float = 100,
        water_depth: float = 95,
        coping_thickness: float = 30,
        elevation: float = -20,
    ) -> str:
        poly = [tuple(p) for p in points]
        obj = self._new(
            {
                "__name__": "swimming-pool.swimming-pool",
                "points": [v2(*p) for p in poly],
                "elevation": elevation,
                "copingThickness": coping_thickness,
                "height": height,
                "filled": True,
                "waterDepth": water_depth,
                "customName": None,
                "area": abs(g.signed_area(poly)),
                "materials": {},
                "baseMaterials": {"swimming-pool.water": "babylonjs:water"},
            }
        )
        self.objects.append(obj)
        return obj["id"]

    def move(self, obj_id: str, dx: float = 0, dy: float = 0, force: bool = False) -> dict:
        """Décale un modèle posé de (dx, dy) cm dans le plan, avec ce qui est posé dessus (lampe, plaid)."""
        obj = self.get(obj_id)
        if obj["__name__"] != "model.model-structure":
            raise PlanError("Seuls les modèles posés se déplacent (pas les murs ni les ouvertures)")
        fp = self.footprint(obj)
        was_inside = self.room_at(fp["center"]) is not None
        top = fp["y0"] + fp["h"]
        carried = [
            o
            for o in self.of_type("model.model-structure")
            if fp["h"] > FLAT_MAX_H
            and o["id"] != obj_id
            and abs(o["position"]["y"] - top) <= ON_TOP_TOLERANCE
            and g.point_in_poly(self.footprint(o)["center"], fp["poly"])
        ]
        moved = [obj, *carried]
        for o in moved:
            o["position"]["x"] += dx
            o["position"]["z"] -= dy
        new = self.footprint(obj)
        room = self.room_at(new["center"])
        geo = self.room_geometry(room["id"]) if room else None
        issues = self.check_footprint(new["poly"], new["y0"], new["h"], geo, {o["id"] for o in moved})
        if was_inside and room is None:
            issues.append("sort des pièces")
        if new["h"] <= FLAT_MAX_H or self._no_collision(obj.get("catalogId") or obj.get("originCatalogId")):
            issues = [i for i in issues if not i.startswith("chevauche")]
        if issues and not force:
            for o in moved:
                o["position"]["x"] -= dx
                o["position"]["z"] += dy
            raise PlanError("Déplacement refusé : " + "; ".join(issues) + " (force=True pour passer outre)")
        return {
            "moved": [o["id"] for o in moved],
            "x": round(new["center"][0], 1),
            "y": round(new["center"][1], 1),
            "room": self.room_label(room) if room else None,
            "warnings": issues,
        }

    def remove(self, obj_id: str) -> list[str]:
        obj = self.get(obj_id)
        doomed = {obj_id}
        if obj["__name__"] == "wall.wall":
            doomed |= {o["id"] for o in self.objects if o.get("parentWallId") == obj_id}
            panes = set(obj.get("paneIds") or {})
            doomed |= panes
            doomed |= {o["id"] for o in self.objects if o.get("paneId") in panes}
            for w in self.of_type("wall.wall"):
                for ext in w["connectionExtremities"]:
                    if ext.get("wallId") == obj_id:
                        ext["wallId"], ext["strong"] = None, False
        if obj["__name__"] in GEOMETRY_TYPES:
            self.geometry_dirty = True
        self.project["layers"][self.floor_id] = [o for o in self.objects if o["id"] not in doomed]
        return sorted(doomed)
