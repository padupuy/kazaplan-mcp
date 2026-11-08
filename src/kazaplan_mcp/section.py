"""Coupes (élévations) d'une pièce : le mur regardé depuis l'intérieur, ses ouvertures et les objets
de la moitié de pièce qui le borde, dessinés d'après leur modèle 3D."""

import math
from html import escape

from . import catalog, mesh
from . import geometry as g
from . import sketch as sk
from .plan import Plan

SLAB = 22
MIN_WALL = 150
NEAR_WALL = 60
MAX_PX = 760
SIDE_WALL = 20

# Silhouette de 1,75 m vue de face, pieds en (0, 0), y vers le bas.
PERSON = (
    "M-7,-148 L7,-148 L20,-141 L24,-100 L20,-80 L16,-82 L15,-118 L13,-92 L13,-50 L10,0 L2,0 L0,-52 "
    "L-2,0 L-10,0 L-13,-50 L-13,-92 L-15,-118 L-16,-82 L-20,-80 L-24,-100 L-20,-141 Z"
)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _frame(edge):
    """Repère de la coupe : observateur tourné vers le mur, abscisse s de gauche à droite depuis le bout
    gauche du mur, profondeur = distance au mur."""
    n = edge["inwardNormal"]
    view = (-n[0], -n[1])
    right = (-view[1], view[0])
    a, b = edge["from"], edge["to"]
    origin = a if _dot((b[0] - a[0], b[1] - a[1]), right) > 0 else b
    return {
        "view": view,
        "right": right,
        "origin": origin,
        "s": lambda p: _dot((p[0] - origin[0], p[1] - origin[1]), right),
        "dist": lambda p: _dot((p[0] - a[0], p[1] - a[1]), n),
    }


def _span(fp, frame):
    s = [frame["s"](p) for p in fp["poly"]]
    return min(s), max(s), min(frame["dist"](p) for p in fp["poly"])


def _walls_for(plan, room):
    polys = [plan.room_poly(r) for r in sk.house_rooms(plan)] or [plan.room_poly(room)]
    return [(w, poly) for w, poly in plan._wall_polys() if sk._borders(w, polys)]


def section_walls(plan: Plan, room_name: str, limit: int = 2) -> list[dict]:
    """Murs qui méritent une coupe : les plus garnis (meubles adossés, ouvertures), au plus limit."""
    room = plan.room(room_name)
    geo = plan.room_geometry(room["id"])
    objects = sk.room_objects(plan, [plan.room_poly(room)], _walls_for(plan, room))
    scored = []
    for e in geo["edges"]:
        if e.get("invisible") or not e["wallId"] or e["length"] < MIN_WALL:
            continue
        frame = _frame(e)
        score = 0.5 * sum(op["width"] for op in e["openings"])
        for o in objects:
            if o["kind"] == "flat":
                continue
            s0, s1, dist = _span(o["fp"], frame)
            if dist < NEAR_WALL:
                score += max(0.0, min(s1, e["length"]) - max(s0, 0))
        if score > 0:
            scored.append((score, e))
    best = sorted(scored, key=lambda t: -t[0])[:limit]
    return [e for _, e in sorted(best, key=lambda t: t[1]["index"])]


def _model_view(o, frame):
    """Paramètres de front_view pour cet objet : axes du .glb (x mirroir de la largeur, -z = face avant)
    projetés sur l'abscisse et la profondeur de la coupe."""
    th = o["fp"]["theta"]
    width_dir, back_dir = (math.cos(th), math.sin(th)), (math.sin(th), -math.cos(th))
    across = (-_dot(width_dir, frame["right"]), _dot(back_dir, frame["right"]))
    toward = (-_dot(width_dir, frame["view"]), _dot(back_dir, frame["view"]))
    return tuple(round(v, 2) + 0.0 for v in across), tuple(round(v, 2) + 0.0 for v in toward)


def _opening(op, s0, s1, px):
    y_top, y_bot = -(op["elevation"] + op["height"]), -op["elevation"]
    w, h = s1 - s0, op["height"]
    sw = f"{1 * px:.2f}"
    out = [
        f'<rect class="{op["kind"]}" x="{s0:.1f}" y="{y_top:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'fill="{"#eef3f6" if op["kind"] == "window" else "#ffffff"}" stroke="{sk.INK}" stroke-width="{sw}"/>'
    ]
    inset = 5
    if op["kind"] == "window":
        leaves = 2 if w > 90 else 1
        lw = (w - 2 * inset) / leaves
        for i in range(leaves):
            x = s0 + inset + i * lw
            out.append(
                f'<rect x="{x:.1f}" y="{y_top + inset:.1f}" width="{lw:.1f}" height="{h - 2 * inset:.1f}" '
                f'fill="none" stroke="{sk.INK}" stroke-width="{0.7 * px:.2f}"/>'
            )
            for k in (0.25, 0.4):
                a = (x + lw * k, y_top + inset + (h - 2 * inset) * 0.3)
                b = (x + lw * (k + 0.15), y_top + inset + (h - 2 * inset) * 0.15)
                out.append(sk._line(a, b, stroke=sk.WINDOW, stroke_width=f"{0.7 * px:.2f}"))
    else:
        out.append(
            f'<circle cx="{s1 - 9:.1f}" cy="{y_bot - 100:.1f}" r="2.5" fill="none" stroke="{sk.INK}" '
            f'stroke-width="{0.8 * px:.2f}"/>'
        )
    return out


def _free_spot(intervals, length, width=60):
    """Centre du plus grand vide au sol (pour la silhouette), ou None."""
    cuts = [(max(0.0, a), min(length, b)) for a, b in intervals if b > 0 and a < length]
    free = g.subtract_intervals((30, length - 30), cuts)
    best = max(free, key=lambda f: f[1] - f[0], default=None)
    return (best[0] + best[1]) / 2 if best and best[1] - best[0] >= width else None


def render(
    plan: Plan, room_name: str, edge: dict, label: str, paint_hex: dict[str, str] | None = None
) -> str:
    """Coupe SVG de la pièce face au mur de l'arête edge (room_geometry), unités en cm, y vers le bas."""
    room = plan.room(room_name)
    poly = plan.room_poly(room)
    frame = _frame(edge)
    length, height = edge["length"], plan.floor["ceilingHeight"]
    depth = max(frame["dist"](p) for p in poly)
    cut = min(depth, max(120, min(depth / 2, 180)))
    objects = sk.room_objects(plan, [poly], _walls_for(plan, room))
    codes = sk.floor_codes(objects)

    span = max(length, height) + 200
    scale = min(1.6, MAX_PX / span)
    px = 1 / scale
    t_side = SIDE_WALL
    pad = 50 + 40 * px
    title_h = 60 * px
    vx, vy = -t_side - pad, -height - SLAB - pad
    vw = length + 2 * t_side + 2 * pad
    bottom = 30 + 34 * px
    vh = height + 2 * SLAB + pad + bottom + title_h

    wall_color = sk.edge_paint(plan, room, edge, paint_hex or {}) or "#ffffff"
    floor_fill = "#d9c3a0" if "parquet" in sk._floor_label(room) else "#d6d3cc"
    body = [
        f'<rect x="{vx:.1f}" y="{vy:.1f}" width="{vw:.1f}" height="{vh:.1f}" fill="{sk.PAPER}"/>',
        f'<rect x="{-t_side}" y="{-height - SLAB}" width="{length + 2 * t_side:.1f}" '
        f'height="{height + 2 * SLAB}" fill="url(#hatch)" stroke="{sk.INK}" stroke-width="{1.2 * px:.2f}"/>',
        f'<rect class="back-wall" x="0" y="{-height}" width="{length:.1f}" height="{height}" '
        'fill="#ffffff"/>',
        f'<rect x="0" y="{-height}" width="{length:.1f}" height="{height}" fill="{wall_color}" '
        'fill-opacity="0.6"/>',
        f'<rect class="floor" x="0" y="-3" width="{length:.1f}" height="3" fill="{floor_fill}"/>',
        f'<clipPath id="room"><rect x="0" y="{-height}" width="{length:.1f}" height="{height}"/></clipPath>',
        '<g clip-path="url(#room)">',
    ]

    ops = []
    for op in edge["openings"]:
        s0, s1 = (
            (op["from"], op["to"])
            if frame["origin"] == edge["from"]
            else (length - op["to"], length - op["from"])
        )
        ops.append((s0, s1, op))
        body += _opening(op, s0, s1, px)

    shown, tags, ground = [], [], []
    for o in objects:
        if o["kind"] == "flat":
            continue
        s0, s1, dist = _span(o["fp"], frame)
        if dist > cut or s1 < 0 or s0 > length:
            continue
        shown.append((dist, s0, s1, o))
        if o["fp"]["y0"] < 50:
            ground.append((s0, s1))
    spot = _free_spot(ground, length)
    if spot is not None:
        shown.append((cut / 2, spot - 25, spot + 25, None))

    for _dist, _s0, _s1, o in sorted(shown, key=lambda t: t[0]):
        if o is None:
            body.append(
                f'<g class="person" transform="translate({spot:.1f} 0)"><circle cx="0" cy="-161" r="10.5" '
                f'fill="#ffffff" stroke="{sk.INK}" stroke-width="{0.9 * px:.2f}"/><path d="{PERSON}" '
                f'fill="#ffffff" fill-opacity="0.9" stroke="{sk.INK}" stroke-width="{0.9 * px:.2f}"/></g>'
            )
            continue
        fp = o["fp"]
        across, toward = _model_view(o, frame)
        half = abs(across[0]) * fp["w"] / 2 + abs(across[1]) * fp["d"] / 2
        sc = frame["s"](fp["center"])
        x, y, w, h = sc - half, -(fp["y0"] + fp["h"]), 2 * half, fp["h"]
        png = mesh.drawing(o["cid"], (fp["w"], fp["h"], fp["d"]), across, toward) if o["cid"] else None
        if png:
            body.append(
                f'<image class="model" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'preserveAspectRatio="none" href="data:image/png;base64,{png}"/>'
            )
        else:
            body.append(
                f'<rect class="model" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'fill="#ffffff" stroke="{sk.INK}" stroke-width="{1 * px:.2f}"/>'
            )
        key = o["cid"] or o["label"]
        if o["kind"] == "floor" and key in codes and all(abs(sc - t) > 18 * px for t, _ in tags):
            c = (min(max(sc, 0), length), SLAB + 14 * px)
            tags.append(
                (
                    sc,
                    f'<circle class="tag" cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="{7.5 * px:.1f}" fill="#ffffff" '
                    f'stroke="{sk.INK}" stroke-width="{0.7 * px:.2f}"/>'
                    + sk._text(c, codes[key], 9 * px, "code", fill=sk.INK, font_weight="600"),
                )
            )
    body.append("</g>")
    body += [t for _, t in tags]

    top = -height - SLAB
    body += sk._dimension((0, top), (length, top), (0, -1), 22 + 22 * px, px)
    marks = sorted({0.0, length, *(v for s0, s1, _ in ops for v in (max(0, s0), min(length, s1)))})
    if len(marks) > 2:
        for a, b in zip(marks, marks[1:], strict=False):
            if b - a > 5:
                body += sk._dimension((a, top), (b, top), (0, -1), 10, px)
    body += sk._dimension((-t_side, 0), (-t_side, -height), (-1, 0), 18, px)
    window = next((op for _, _, op in ops if op["kind"] == "window"), None)
    if window:
        levels = [0, window["elevation"], window["elevation"] + window["height"], height]
        for a, b in zip(levels, levels[1:], strict=False):
            if b - a > 5:
                body += sk._dimension((length + t_side, -a), (length + t_side, -b), (1, 0), 18, px)

    ty = SLAB + bottom + title_h / 2 - 14 * px
    notes = []
    mid = (room.get("materials") or {}).get("flooring", "").removeprefix("catalog:")
    if item := catalog.get(mid) if mid else None:
        notes.append(f"Sol : {sk.clean(item['label'])}")
    notes.append(f"Hauteur sous plafond {sk._meters(height)} m")
    body.append(
        sk._line(
            (vx + 20 * px, ty - 16 * px), (vx + vw - 20 * px, ty - 16 * px), stroke=sk.INK, stroke_width=px
        )
    )
    body.append(
        f'<text class="title" x="{vx + 20 * px:.1f}" y="{ty:.1f}" font-size="{13 * px:.1f}" '
        f'dominant-baseline="central" fill="{sk.INK}"><tspan font-weight="700">Coupe {escape(label)}</tspan>'
        f'<tspan fill="{sk.MUTED}" dx="{6 * px:.1f}">/ {escape(plan.room_label(room))}</tspan></text>'
    )
    body.append(
        f'<text x="{vx + 20 * px:.1f}" y="{ty + 17 * px:.1f}" font-size="{10 * px:.1f}" '
        f'dominant-baseline="central" fill="{sk.MUTED}">{escape(" · ".join(notes))}</text>'
    )
    body.append(sk._scale_bar(vx + vw - 20 * px - 200, ty - 4 * px, px))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.0f} {vy:.0f} {vw:.0f} {vh:.0f}" '
        f'width="{vw * scale:.0f}" height="{vh * scale:.0f}" font-family="{sk.FONT}">\n'
        + sk.DEFS
        + "\n"
        + "\n".join(body)
        + "\n</svg>\n"
    )
