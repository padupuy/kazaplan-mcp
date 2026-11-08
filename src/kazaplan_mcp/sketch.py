"""Plans SVG des pièces et planches de décoration en Markdown.

python -m kazaplan_mcp.sketch board <plan_id | plan.kzp> <DECOR.md>
    écrit PLANCHES.md, plans/*.svg et swatches/*.svg à côté du DECOR.md ;
    avec un id, lit la dernière copie horodatée du dossier des sauvegardes
"""

import math
import re
import string
import sys
import unicodedata
from html import escape
from pathlib import Path

import yaml

from . import api, catalog, section
from . import geometry as g
from .plan import Plan, pt

LETTERS = string.ascii_uppercase + string.ascii_lowercase + string.digits
OUTSIDE_TYPES = {"terraceext"}
HOUSE_GAP = 60
FLAT_MAX_H = 2
WALL_ITEM_MIN_ELEVATION = 40
WALL_TOUCH = 6
ON_TOP_MIN_ELEVATION = 25
CEILING_MARGIN = 20
PAINT_WIDTH = 7
WALL_REACH = 40
MAX_PX = 1000
REF = re.compile(r"\{([\w.-]+)\}")

PAPER = "#fbfaf7"
GRID = "#ece8e1"
INK = "#2f2b27"
MUTED = "#8c857c"
DIM = "#c4553a"
RUG = "#c9ad86"
LIGHT = "#d2a23c"
WALL_ITEM = "#b07d48"
WINDOW = "#7d9db5"
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"

DEFS = f"""<defs>
<pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse">
<path d="M50 0H0V50" fill="none" stroke="{GRID}" stroke-width="0.8"/></pattern>
<pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
<rect width="7" height="7" fill="#e6e1d8"/>
<line x1="0" y1="0" x2="0" y2="7" stroke="#9d958a" stroke-width="1.3"/>
</pattern>
<pattern id="parquet" width="90" height="26" patternUnits="userSpaceOnUse">
<rect width="90" height="26" fill="#f4ecdf"/>
<path d="M0 0H90M0 13H90M0 0V13M45 13V26" stroke="#e3d5bf" stroke-width="0.9" fill="none"/></pattern>
<pattern id="herringbone" width="26" height="26" patternUnits="userSpaceOnUse">
<rect width="26" height="26" fill="#f4ecdf"/>
<path d="M0 13L13 0L26 13M0 26L13 13L26 26M13 0V13M0 13V26M26 13V26"
stroke="#e3d5bf" stroke-width="0.9" fill="none"/>
</pattern>
<pattern id="tile" width="40" height="40" patternUnits="userSpaceOnUse">
<rect width="40" height="40" fill="#f2f1ed"/>
<path d="M40 0H0V40" stroke="#dfdbd3" stroke-width="0.9" fill="none"/>
</pattern>
<pattern id="weave" width="6" height="6" patternUnits="userSpaceOnUse">
<rect width="6" height="6" fill="{RUG}" fill-opacity="0.22"/>
<circle cx="3" cy="3" r="0.6" fill="{RUG}" fill-opacity="0.8"/></pattern>
</defs>"""


def _bbox(polys):
    xs = [p[0] for poly in polys for p in poly]
    ys = [p[1] for poly in polys for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _near(a, b, gap):
    return a[0] - gap <= b[2] and b[0] - gap <= a[2] and a[1] - gap <= b[3] and b[1] - gap <= a[3]


def house_rooms(plan: Plan) -> list[dict]:
    """Pièces du bâtiment principal : la plus grande et celles qui la jouxtent, de proche en proche
    (garage ou pool house éloignés exclus, terrasse exclue)."""
    rooms = [r for r in plan.of_type("wall.room") if r.get("type") not in OUTSIDE_TYPES]
    if not rooms:
        return []
    boxes = {r["id"]: _bbox([plan.room_poly(r)]) for r in rooms}
    rooms.sort(key=lambda r: -abs(g.signed_area(plan.room_poly(r))))
    kept, rest = [rooms[0]], rooms[1:]
    grew = True
    while grew:
        grew = False
        for r in list(rest):
            if any(_near(boxes[r["id"]], boxes[k["id"]], HOUSE_GAP) for k in kept):
                kept.append(r)
                rest.remove(r)
                grew = True
    return kept


def _seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _borders(wall, polys):
    a, b = (pt(x["position"]) for x in wall["connectionExtremities"])
    samples = [(a[0] + (b[0] - a[0]) * i / 4, a[1] + (b[1] - a[1]) * i / 4) for i in range(5)]
    segs = [(p, q) for poly in polys for p, q in zip(poly, poly[1:] + poly[:1], strict=True)]
    return any(min(_seg_dist(s, p, q) for p, q in segs) <= WALL_REACH for s in samples)


def _points(poly):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in poly)


def _attrs(attrs):
    return "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())


def _poly(poly, cls, **attrs):
    return f'<polygon class="{cls}" points="{_points(poly)}"{_attrs(attrs)}/>'


def _line(a, b, **attrs):
    return f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}"{_attrs(attrs)}/>'


def _text(p, text, size, cls="label", anchor="middle", **attrs):
    return (
        f'<text class="{cls}" x="{p[0]:.1f}" y="{p[1]:.1f}" font-size="{size:.1f}" text-anchor="{anchor}" '
        f'dominant-baseline="central"{_attrs(attrs)}>{escape(text)}</text>'
    )


def clean(label: str) -> str:
    return " ".join(label.split())


def _dims(fp):
    return f"{round(fp['w'])} × {round(fp['d'])}"


def _meters(cm):
    return f"{cm / 100:.2f}".replace(".", ",")


def area_m2(plan, room) -> float:
    return abs(g.signed_area(plan.room_poly(room))) / 10000


def _floor_label(room):
    mid = (room.get("materials") or {}).get("flooring", "").removeprefix("catalog:")
    item = catalog.get(mid) if mid else None
    return item["label"].lower() if item else ""


def _floor_fill(room):
    label = _floor_label(room)
    if "parquet" not in label:
        return "url(#tile)"
    return "url(#herringbone)" if "bâton" in label or "chevron" in label else "url(#parquet)"


def edge_paint(plan, room, edge, paint_hex) -> str | None:
    """Couleur de palette de la peinture posée sur le mur de cette arête, côté pièce."""
    if not edge["wallId"] or edge.get("invisible"):
        return None
    mats = [
        (p.get("materials") or {}).get("wall.pane", "").removeprefix("catalog:")
        for p in plan.room_panes(room)
        if (p.get("wallInfo") or {}).get("id") == edge["wallId"]
    ]
    return next((paint_hex[m] for m in mats if m in paint_hex), None)


def _paint_lines(plan, room, paint_hex):
    try:
        geo = plan.room_geometry(room["id"])
    except Exception:
        return []
    out = []
    for e in geo["edges"]:
        color = edge_paint(plan, room, e, paint_hex)
        if not color:
            continue
        n, off = e["inwardNormal"], PAINT_WIDTH / 2
        a = (e["from"][0] + n[0] * off, e["from"][1] + n[1] * off)
        b = (e["to"][0] + n[0] * off, e["to"][1] + n[1] * off)
        out.append(_line(a, b, **{"class": "paint", "stroke": color, "stroke_width": PAINT_WIDTH}))
    return out


def _dimension(a, b, n, offset, px):
    """Cote de a à b, reportée de offset selon n, valeur en mètres."""
    p = (a[0] + n[0] * offset, a[1] + n[1] * offset)
    q = (b[0] + n[0] * offset, b[1] + n[1] * offset)
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    tick = 4 * px
    out = [
        _line(a, (p[0] + n[0] * tick, p[1] + n[1] * tick), stroke=DIM, stroke_width=f"{0.5 * px:.2f}"),
        _line(b, (q[0] + n[0] * tick, q[1] + n[1] * tick), stroke=DIM, stroke_width=f"{0.5 * px:.2f}"),
        _line(p, q, stroke=DIM, stroke_width=f"{0.8 * px:.2f}"),
    ]
    for c in (p, q):
        out.append(
            _line(
                (c[0] - tick, c[1] + tick),
                (c[0] + tick, c[1] - tick),
                stroke=DIM,
                stroke_width=f"{1.2 * px:.2f}",
            )
        )
    mid = ((p[0] + q[0]) / 2 + n[0] * 8 * px, (p[1] + q[1]) / 2 + n[1] * 8 * px)
    rotate = ' transform="rotate(-90 {:.1f} {:.1f})"'.format(*mid) if abs(n[0]) > abs(n[1]) else ""
    out.append(
        f'<text class="dim" x="{mid[0]:.1f}" y="{mid[1]:.1f}" font-size="{10 * px:.1f}" text-anchor="middle" '
        f'dominant-baseline="central" fill="{DIM}"{rotate}>{_meters(length)}</text>'
    )
    return out


def _light(c, px):
    r = 7 * px
    x, y = c
    return (
        f'<g class="light"><circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#ffffff" stroke="{INK}" '
        f'stroke-width="{0.9 * px:.2f}"/>'
        f'<path d="M{x:.1f} {y:.1f}L{x + r:.1f} {y:.1f}A{r:.1f} {r:.1f} 0 0 1 {x:.1f} {y + r:.1f}Z'
        f'M{x:.1f} {y:.1f}L{x - r:.1f} {y:.1f}A{r:.1f} {r:.1f} 0 0 1 {x:.1f} {y - r:.1f}Z" '
        f'fill="{LIGHT}"/></g>'
    )


def _door(c, u, n, width, thickness, px, inside):
    """Battant et arc d'ouverture, côté pièce dessinée."""
    side = 1 if inside((c[0] + n[0] * (thickness / 2 + 15), c[1] + n[1] * (thickness / 2 + 15))) else -1
    s = (n[0] * side, n[1] * side)
    face = (c[0] + s[0] * thickness / 2, c[1] + s[1] * thickness / 2)
    hinge = (face[0] - u[0] * width / 2, face[1] - u[1] * width / 2)
    end = (face[0] + u[0] * width / 2, face[1] + u[1] * width / 2)
    tip = (hinge[0] + s[0] * width, hinge[1] + s[1] * width)
    v, w = (tip[0] - hinge[0], tip[1] - hinge[1]), (end[0] - hinge[0], end[1] - hinge[1])
    sweep = 1 if v[0] * w[1] - v[1] * w[0] > 0 else 0
    return [
        _line(hinge, tip, stroke=INK, stroke_width=f"{1.2 * px:.2f}"),
        f'<path d="M{tip[0]:.1f} {tip[1]:.1f}A{width:.1f} {width:.1f} 0 0 {sweep} {end[0]:.1f} {end[1]:.1f}" '
        f'fill="none" stroke="{MUTED}" stroke-width="{0.7 * px:.2f}" '
        f'stroke-dasharray="{3 * px:.1f} {2 * px:.1f}"/>',
    ]


def _section_marker(label, edge, px):
    """Repère de coupe : pastille numérotée à 45 cm du mur, pointe tournée vers lui."""
    n = edge["inwardNormal"]
    mid = ((edge["from"][0] + edge["to"][0]) / 2, (edge["from"][1] + edge["to"][1]) / 2)
    r = 9 * px
    c = (mid[0] + n[0] * (30 + r * 2), mid[1] + n[1] * (30 + r * 2))
    tip = (c[0] - n[0] * r * 2, c[1] - n[1] * r * 2)
    side = (-n[1] * r * 0.9, n[0] * r * 0.9)
    tri = [tip, (c[0] + side[0], c[1] + side[1]), (c[0] - side[0], c[1] - side[1])]
    return (
        '<g class="section-marker">'
        + _poly(tri, "section-arrow", fill=DIM)
        + f'<circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="{r:.1f}" fill="#ffffff" stroke="{DIM}" '
        f'stroke-width="{1.2 * px:.2f}"/>'
        + _text(c, label, 10 * px, "section-label", fill=DIM, font_weight="700")
        + "</g>"
    )


def _scale_bar(x, y, px):
    out = []
    for i in range(2):
        fill = INK if i % 2 == 0 else "#ffffff"
        out.append(
            f'<rect x="{x + i * 100}" y="{y - 2.5 * px:.1f}" width="100" height="{5 * px:.1f}" fill="{fill}" '
            f'stroke="{INK}" stroke-width="{0.8 * px:.2f}"/>'
        )
    for i, t in enumerate(("0", "1", "2 m")):
        out.append(_text((x + i * 100, y + 11 * px), t, 9 * px, "scale-label", fill=MUTED))
    return '<g class="scale">' + "".join(out) + "</g>"


def room_objects(plan: Plan, polys, walls) -> list[dict]:
    """Objets posés dans les pièces polys, classés : flat (tapis), wall (au mur), light (au plafond),
    on_top (posé sur un meuble), floor (meuble au sol)."""
    ceiling = plan.floor["ceilingHeight"]

    def on_wall(fp):
        grown = g.obb(fp["center"], fp["w"] + 2 * WALL_TOUCH, fp["d"] + 2 * WALL_TOUCH, fp["theta"])
        return any(g.polys_overlap(grown, poly) for _, poly in walls)

    out = []
    for o in plan.of_type("model.model-structure"):
        fp = plan.footprint(o)
        if not any(g.point_in_poly(fp["center"], poly) for poly in polys):
            continue
        # originCatalogId = article choisi ; catalogId peut désigner le modèle de base d'une variante
        # (plaid « Lazo vert » model-65253 → catalogId model-64800 « Aubin »).
        cid = next((c for c in (o.get("originCatalogId"), o.get("catalogId")) if c and catalog.get(c)), None)
        label = clean(catalog.get(cid)["label"]) if cid else o.get("catalogId") or "?"
        if fp["h"] <= FLAT_MAX_H:
            kind = "flat"
        elif fp["y0"] >= WALL_ITEM_MIN_ELEVATION and on_wall(fp):
            kind = "wall"
        elif fp["y0"] >= ON_TOP_MIN_ELEVATION and fp["y0"] + fp["h"] >= ceiling - CEILING_MARGIN:
            kind = "light"
        elif fp["y0"] >= ON_TOP_MIN_ELEVATION:
            kind = "on_top"
        else:
            kind = "floor"
        out.append({"kind": kind, "fp": fp, "cid": cid, "label": label, "obj": o})
    return out


def floor_codes(objects: list[dict]) -> dict[str, str]:
    """Lettre de chaque modèle posé au sol (clé : id catalogue ou libellé), du plus grand au plus petit."""
    codes: dict[str, str] = {}
    for o in sorted((o for o in objects if o["kind"] == "floor"), key=lambda o: -o["fp"]["w"] * o["fp"]["d"]):
        key = o["cid"] or o["label"]
        if key not in codes:
            codes[key] = LETTERS[len(codes) % len(LETTERS)]
    return codes


def render(
    plan: Plan,
    room: str | None = None,
    paint_hex: dict[str, str] | None = None,
    sections: list[tuple[str, dict]] | None = None,
) -> dict:
    """Plan SVG vu de dessus d'une pièce (ou du bâtiment principal), axe y vers le bas comme dans le
    planner, unités en cm. Pièce : une lettre par modèle (legend) ; vue d'ensemble : noms des pièces.
    paint_hex (material-… → couleur) trace la peinture de chaque mur en liseré ; sections ((numéro, arête
    de room_geometry)) place le repère de chaque coupe, flèche vers le mur regardé."""
    paint_hex = paint_hex or {}
    rooms = [plan.room(room)] if room else house_rooms(plan)
    polys = [plan.room_poly(r) for r in rooms]
    x0, y0, x1, y1 = _bbox(polys)
    span = max(x1 - x0, y1 - y0) + 160
    scale = min(2.0, MAX_PX / span)
    px = 1 / scale
    pad = 40 + 34 * px
    title_h = 46 * px
    vx, vy = x0 - pad, y0 - pad
    vw, vh = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad + title_h
    shown = house_rooms(plan) if room else rooms
    shown_polys = [plan.room_poly(r) for r in shown]
    # Murs de clôture ou de jardin exclus : seuls ceux qui bordent une pièce dessinée.
    walls = [(w, poly) for w, poly in plan._wall_polys() if _borders(w, shown_polys)]

    def inside(p):
        return any(g.point_in_poly(p, poly) for poly in polys)

    objects = room_objects(plan, polys, walls)
    flat = [o["fp"] for o in objects if o["kind"] == "flat"]
    floor_items = [(o["fp"], o["cid"], o["label"]) for o in objects if o["kind"] == "floor"]
    wall_fps = [o["fp"] for o in objects if o["kind"] == "wall"]
    lights = [(o["fp"], o["label"]) for o in objects if o["kind"] == "light"]
    wall_items, on_top, schedule = [], [], []
    for o in objects:
        fp, label = o["fp"], o["label"]
        if o["kind"] == "flat":
            schedule.append(("", label, _dims(fp), "au sol"))
        elif o["kind"] == "wall":
            wall_items.append(f"{label} ({round(fp['w'])} × {round(fp['h'])}, à {round(fp['y0'])} cm)")
            schedule.append(
                ("", label, f"{round(fp['w'])} × {round(fp['h'])}", f"au mur, à {round(fp['y0'])} cm")
            )
        elif o["kind"] == "light":
            schedule.append(("", label, "", "plafond"))
        elif o["kind"] == "on_top":
            on_top.append(f"{label} (à {round(fp['y0'])} cm)")
            schedule.append(("", label, "", f"sur un meuble, à {round(fp['y0'])} cm"))

    body = [
        f'<rect x="{vx:.1f}" y="{vy:.1f}" width="{vw:.1f}" height="{vh:.1f}" fill="{PAPER}"/>',
        f'<rect x="{vx:.1f}" y="{vy:.1f}" width="{vw:.1f}" height="{vh:.1f}" fill="url(#grid)"/>',
        f'<clipPath id="sheet"><rect x="{vx:.1f}" y="{vy:.1f}" width="{vw:.1f}" '
        f'height="{vh - title_h:.1f}"/></clipPath>',
        '<g clip-path="url(#sheet)">',
    ]
    for r in shown:
        body.append(_poly(plan.room_poly(r), "floor", fill=_floor_fill(r)))
    for fp in flat:
        body.append(
            _poly(
                fp["poly"],
                "rug",
                fill="url(#weave)",
                stroke="#a88a63",
                stroke_width=f"{0.8 * px:.2f}",
                stroke_dasharray=f"{4 * px:.1f} {2 * px:.1f}",
            )
        )
    for r in rooms:
        body += _paint_lines(plan, r, paint_hex)

    codes = floor_codes(objects)
    legend, labels, furniture, seen = [], [], [], set()
    for fp, cid, label in sorted(floor_items, key=lambda t: -t[0]["w"] * t[0]["d"]):
        shadow = [(x + 5 * px, y + 5 * px) for x, y in fp["poly"]]
        body.append(_poly(shadow, "shadow", fill="#000000", fill_opacity="0.06"))
        furniture.append(
            _poly(fp["poly"], "furniture", fill="#ffffff", stroke=INK, stroke_width=f"{1.1 * px:.2f}")
        )
        if not room:
            continue
        key = cid or label
        if key not in seen:
            seen.add(key)
            legend.append(f"{codes[key]}  {label} ({_dims(fp)})")
        schedule.append((codes[key], label, _dims(fp), "au sol"))
        r = 7.5 * px
        c = fp["center"]
        labels.append(
            f'<circle class="tag" cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="{r:.1f}" fill="#ffffff" stroke="{INK}" '
            f'stroke-width="{0.7 * px:.2f}"/>'
        )
        labels.append(_text(c, codes[key], 9 * px, "code", fill=INK, font_weight="600"))
    body += furniture
    for fp in wall_fps:
        body.append(
            _poly(
                fp["poly"],
                "wall-item",
                fill=WALL_ITEM,
                fill_opacity="0.3",
                stroke=WALL_ITEM,
                stroke_width=f"{0.9 * px:.2f}",
            )
        )

    for _, poly in walls:
        body.append(_poly(poly, "wall", fill="url(#hatch)", stroke=INK, stroke_width=f"{1.3 * px:.2f}"))
    wall_by_id = {w["id"]: w for w, _ in walls}
    for op in plan._openings():
        w = wall_by_id.get(op["wallId"])
        if not w:
            continue
        a, b = (pt(x["position"]) for x in w["connectionExtremities"])
        length = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
        u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        n = (-u[1], u[0])
        c, half, t = op["center"], op["width"] / 2, w["thickness"]
        start = (c[0] - u[0] * half - n[0] * (t + 2) / 2, c[1] - u[1] * half - n[1] * (t + 2) / 2)
        gap = g.rect_on_edge(start, u, n, 0, op["width"], t + 2)
        p, q = (c[0] - u[0] * half, c[1] - u[1] * half), (c[0] + u[0] * half, c[1] + u[1] * half)
        if op["kind"] == "door":
            body.append(_poly(gap, "door", fill=PAPER))
            if any(_seg_dist(c, e["a"], e["b"]) <= t / 2 + 5 for poly in polys for e in g.edges(poly)):
                body += _door(c, u, n, op["width"], t, px, inside)
        else:
            body.append(_poly(gap, "window", fill="#ffffff", stroke=INK, stroke_width=f"{0.8 * px:.2f}"))
            for k in (-2.5, 2.5):
                o = (n[0] * k, n[1] * k)
                body.append(
                    _line(
                        (p[0] + o[0], p[1] + o[1]),
                        (q[0] + o[0], q[1] + o[1]),
                        stroke=WINDOW,
                        stroke_width=f"{1 * px:.2f}",
                    )
                )

    for fp, _ in lights:
        body.append(_light(fp["center"], px))
    body += labels
    for label, e in sections or []:
        body.append(_section_marker(label, e, px))

    if room:
        hole = " ".join(f"M{_points(poly).replace(' ', ' L')} Z" for poly in polys)
        body.append(
            f'<mask id="around"><rect x="{vx:.1f}" y="{vy:.1f}" width="{vw:.1f}" height="{vh:.1f}" '
            'fill="#fff"/>'
            f'<path d="{hole}" fill="#000" stroke="#000" stroke-width="70" stroke-linejoin="round"/></mask>'
            f'<rect x="{vx:.1f}" y="{vy:.1f}" width="{vw:.1f}" height="{vh:.1f}" fill="{PAPER}" '
            'fill-opacity="0.82" mask="url(#around)"/>'
        )
    else:
        for r, poly in zip(rooms, polys, strict=True):
            c = g.centroid(poly)
            halo = {"stroke": PAPER, "stroke_width": f"{4 * px:.1f}", "paint_order": "stroke"}
            body.append(
                _text((c[0], c[1] - 7 * px), plan.room_label(r), 12 * px, fill=INK, font_weight="600", **halo)
            )
            area = f"{area_m2(plan, r):.1f} m²".replace(".", ",")
            body.append(_text((c[0], c[1] + 8 * px), area, 10 * px, "area", fill=MUTED, **halo))

    body.append("</g>")
    off = 30 + 12 * px
    body += _dimension((x0, y0), (x1, y0), (0, -1), off, px)
    body += _dimension((x0, y0), (x0, y1), (-1, 0), off, px)

    ty = y1 + pad + title_h / 2 - 6 * px
    title = plan.room_label(rooms[0]) if room else "Vue d'ensemble"
    subtitle = f"Plan d'aménagement · {sum(area_m2(plan, r) for r in rooms):.1f} m²".replace(".", ",")
    body.append(
        _line((vx + 20 * px, ty - 16 * px), (vx + vw - 20 * px, ty - 16 * px), stroke=INK, stroke_width=px)
    )
    body.append(
        f'<text class="title" x="{vx + 20 * px:.1f}" y="{ty:.1f}" font-size="{13 * px:.1f}" '
        f'dominant-baseline="central" fill="{INK}"><tspan font-weight="700">{escape(title)}</tspan>'
        f'<tspan fill="{MUTED}" dx="{6 * px:.1f}">/ {escape(subtitle)}</tspan></text>'
    )
    body.append(_scale_bar(vx + vw - 20 * px - 200, ty - 4 * px, px))
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.0f} {vy:.0f} {vw:.0f} {vh:.0f}" '
        f'width="{vw * scale:.0f}" height="{vh * scale:.0f}" font-family="{FONT}">\n'
        + DEFS
        + "\n"
        + "\n".join(body)
        + "\n</svg>\n"
    )
    return {
        "svg": svg,
        "legend": legend,
        "wall": wall_items if room else [],
        "on_top": on_top if room else [],
        "ceiling": [label for _, label in lights] if room else [],
        "schedule": schedule if room else [],
    }


def _resolve(value, decor):
    if not isinstance(value, str):
        return value
    m = REF.fullmatch(value.strip())
    if not m:
        return value
    node = decor
    for k in m.group(1).split("."):
        node = node.get(k) if isinstance(node, dict) else None
    return node


def _token(value):
    m = REF.fullmatch(value.strip()) if isinstance(value, str) else None
    return m.group(1).split(".")[-1] if m else None


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def swatch_svg(hex_color: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28">'
        f'<rect x="0.5" y="0.5" width="27" height="27" rx="3" fill="{hex_color}" stroke="#00000026"/></svg>\n'
    )


def paint_colors(decor: dict) -> dict[str, str]:
    colors = decor.get("colors") or {}
    return {mid: colors[tok] for tok, mid in (decor.get("paints") or {}).items() if tok in colors}


def _paint_item(decor, token):
    mid = (decor.get("paints") or {}).get(token)
    item = catalog.get(mid) if mid else None
    return mid, clean(item["label"]) if item else None


def palette_svg(decor: dict) -> str:
    """Nuancier de la maison en cartes : aplat, jeton, hexadécimal, peinture du catalogue."""
    colors = decor.get("colors") or {}
    cols, cw, ch, gap = 4, 160, 200, 18
    rows = math.ceil(len(colors) / cols) or 1
    w, h = cols * cw + (cols - 1) * gap, rows * (ch + gap) - gap
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'font-family="{FONT}">'
    ]
    for i, (token, hex_color) in enumerate(colors.items()):
        x, y = (i % cols) * (cw + gap), (i // cols) * (ch + gap)
        mid, label = _paint_item(decor, token)
        out.append(
            f'<rect x="{x + 0.5}" y="{y + 0.5}" width="{cw - 1}" height="{ch - 1}" fill="#ffffff" '
            'stroke="#e4e0d8"/>'
            f'<rect x="{x + 10}" y="{y + 10}" width="{cw - 20}" height="{ch - 82}" fill="{hex_color}"/>'
        )
        lines = [
            (14, INK, "700", token),
            (11, MUTED, "400", hex_color.upper()),
            (11, INK, "400", label or "teinte de matière"),
            (10, MUTED, "400", mid or ""),
        ]
        ty = y + ch - 62
        for size, fill, weight, text in lines:
            out.append(
                f'<text x="{x + 12}" y="{ty}" font-size="{size}" font-weight="{weight}" fill="{fill}">'
                f"{escape(text)}</text>"
            )
            ty += size + 4
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _swatch(token):
    return f"![{token}](swatches/{token}.svg)"


def _paint_row(decor, zone, token):
    hex_color = (decor.get("colors") or {}).get(token)
    if not hex_color:
        return None
    mid, label = _paint_item(decor, token)
    ref = f"`{mid}`" if mid else ""
    return f"| {zone} | {_swatch(token)} | **{label or token}** · {token} `{hex_color}` | {ref} |"


def _schedule(out):
    """Nomenclature : une ligne par article et emplacement, quantités regroupées, codes du plan d'abord."""
    rows: dict[tuple, list] = {}
    for code, label, dims, where in out["schedule"]:
        row = rows.setdefault((code, label, where), [0, []])
        row[0] += 1
        if dims and dims not in row[1]:
            row[1].append(dims)
    if not rows:
        return []
    order = ("au sol", "au mur", "sur un meuble", "plafond")

    def key(k):
        code, label, where = k
        spot = next(i for i, o in enumerate(order) if where.startswith(o))
        return (code == "", LETTERS.find(code), spot, where, label)

    lines = ["| | Élément | Qté | Dimensions (cm) | Emplacement |", "|:-:|---|:-:|---|---|"]
    for k in sorted(rows, key=key):
        code, label, where = k
        qty, dims = rows[k]
        lines.append(f"| {f'**{code}**' if code else '·'} | {label} | {qty} | {' / '.join(dims)} | {where} |")
    return lines + [""]


LEGEND = (
    "Vue de dessus, comme le plan 2D du planner, cotes en mètres. Murs hachurés, liseré intérieur = peinture "
    "du mur ; sols parquet ou carrelage ; portes avec leur débattement, fenêtres en double trait bleu ; "
    "tapis en pointillé, luminaires de plafond ◐, objets muraux en brun."
)


def board(plan: Plan, decor: dict) -> tuple[str, dict[str, str]]:
    """Planches de la maison : vue d'ensemble et palette, puis une section par pièce du DECOR.md (plan SVG,
    revêtements, nomenclature). Renvoie le Markdown et les fichiers à écrire à côté
    (chemin relatif → contenu)."""
    colors = decor.get("colors") or {}
    paints = paint_colors(decor)
    files = {f"swatches/{k}.svg": swatch_svg(v) for k, v in colors.items()}
    files["swatches/palette.svg"] = palette_svg(decor)
    files["plans/maison.svg"] = render(plan, paint_hex=paints)["svg"]

    sections, summary = [], []
    for key, room in (decor.get("rooms") or {}).items():
        name = room.get("name")
        try:
            r = plan.room(name)
        except Exception:
            continue
        num = f"{len(summary) + 1:02d}"
        floor = _resolve(room.get("floor"), decor)
        floor_ref = floor.get("catalog") if isinstance(floor, dict) else None
        item = catalog.get(floor_ref) if floor_ref else None
        floor_label = clean(item["label"]) if item else floor_ref or ""
        walls_token = _token(room.get("walls"))
        area = f"{area_m2(plan, r):.1f} m²".replace(".", ",")
        anchor = re.sub(r"[^\w\- ]", "", f"{num} · {name}".lower()).replace(" ", "-")
        swatch = _swatch(walls_token) if walls_token in colors else ""
        summary.append(f"| {num} | [{name}](#{anchor}) | {area} | {swatch} | {floor_label} |")

        md = [f"## {num} · {name}", ""]
        who = " · ".join(x for x in [room.get("users")] + list(room.get("uses") or []) if x)
        md += [f"`{area}`" + (f" — *{who}*" if who else ""), ""]
        cuts = [(str(i), e) for i, e in enumerate(section.section_walls(plan, name), 1)]
        out = render(plan, name, paint_hex=paints, sections=cuts)
        path = f"plans/{slug(key)}.svg"
        files[path] = out["svg"]
        md += [f"![{name}]({path})", ""]
        views = []
        for label, e in cuts:
            cut_path = f"plans/{slug(key)}-coupe-{label}.svg"
            files[cut_path] = section.render(plan, name, e, label, paints)
            views.append(f"![Coupe {label}]({cut_path})")
        if views:
            md += [" ".join(views), ""]

        rows = []
        for field, zone in (("walls", "Murs"), ("ceiling", "Plafond")):
            if (t := _token(room.get(field))) and (row := _paint_row(decor, zone, t)):
                rows.append(row)
        accent = room.get("accent") or {}
        if (t := _token(accent.get("color"))) and (
            row := _paint_row(decor, f"Accent — {accent.get('wall', '')}".rstrip(" —"), t)
        ):
            rows.append(row)
        if floor_label:
            rows.append(f"| Sol | | {floor_label} | `{floor_ref}` |")
        if rows:
            md += ["**Revêtements**", "", "| Zone | | Matière | Référence |", "|---|:-:|---|---|", *rows, ""]
        if sched := _schedule(out):
            md += ["**Nomenclature**", "", *sched]
        sections += md

    md = [f"# {decor.get('name', 'Planches')}", ""]
    if decor.get("description"):
        md += [f"> {decor['description']}", ""]
    md += ["## Vue d'ensemble", "", "![Vue d'ensemble](plans/maison.svg)", "", f"<sub>{LEGEND}</sub>", ""]
    md += ["### Palette", "", "![Palette](swatches/palette.svg)", ""]
    if summary:
        md += ["### Pièces", "", "| | Pièce | Surface | Murs | Sol |", "|:-:|---|--:|:-:|---|", *summary, ""]
    md += sections
    return "\n".join(md).rstrip() + "\n", files


def read_decor(path: Path) -> dict:
    return yaml.safe_load(path.read_text().split("---")[1])


def plan_source(ref: str) -> Path:
    if not ref.isdigit():
        return Path(ref)
    stamped = re.compile(rf"{ref}-\d{{8}}-\d{{6}}-\w+\.kzp")
    copies = sorted(p for p in api.BACKUPS.glob(f"{ref}-*.kzp") if stamped.fullmatch(p.name))
    if not copies:
        raise SystemExit(f"Aucune copie de {ref} dans {api.BACKUPS}")
    return copies[-1]


def write_board(plan: Plan, decor_path: Path) -> dict:
    """Écrit PLANCHES.md, plans/ et swatches/ à côté du DECOR.md, sans jamais sortir de son dossier."""
    if decor_path.name != "DECOR.md" or not decor_path.is_file():
        raise ValueError(f"{decor_path} : un fichier DECOR.md existant est attendu")
    out = decor_path.resolve().parent
    md, files = board(plan, read_decor(decor_path))
    files["PLANCHES.md"] = md
    written = []
    for rel, content in files.items():
        target = out / rel
        if target.is_symlink() or not target.resolve().is_relative_to(out):
            raise ValueError(f"Chemin refusé : {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        written.append(rel)
    return {"board": str(out / "PLANCHES.md"), "files": sorted(written)}


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] != "board":
        print(__doc__)
        return 1
    plan = Plan.from_bytes(plan_source(argv[2]).read_bytes())
    print(write_board(plan, Path(argv[3]))["board"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
