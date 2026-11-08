"""Géométrie 2D du plan (cm). Plan = (x, y) ; scène 3D Kazaplan = (x, hauteur, -y)."""

import math

Pt = tuple[float, float]


def signed_area(poly: list[Pt]) -> float:
    return (
        sum(
            poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
            for i in range(len(poly))
        )
        / 2
    )


def centroid(poly: list[Pt]) -> Pt:
    a = signed_area(poly)
    if abs(a) < 1e-9:
        return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))
    cx = cy = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        f = x0 * y1 - x1 * y0
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    return (cx / (6 * a), cy / (6 * a))


def point_in_poly(p: Pt, poly: list[Pt]) -> bool:
    x, y = p
    inside = False
    for i in range(len(poly)):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % len(poly)]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def edges(poly: list[Pt]):
    """Arêtes du polygone avec normale intérieure unitaire."""
    ccw = signed_area(poly) > 0
    out = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        u = (dx / length, dy / length)
        n = (-u[1], u[0]) if ccw else (u[1], -u[0])
        out.append({"index": i, "a": a, "b": b, "length": length, "u": u, "n": n})
    return out


def project(p: Pt, a: Pt, u: Pt) -> tuple[float, float]:
    """(abscisse le long de a+t·u, distance signée à gauche de u)."""
    dx, dy = p[0] - a[0], p[1] - a[1]
    return dx * u[0] + dy * u[1], dx * -u[1] + dy * u[0]


def obb(center: Pt, w: float, d: float, theta: float) -> list[Pt]:
    """Empreinte d'un objet : largeur sur l'axe local x (direction theta), profondeur sur
    l'axe local z, qui pointe dans le plan vers theta - 90°. La face avant (local -z)
    regarde vers theta + 90°."""
    ux, uy = math.cos(theta), math.sin(theta)
    vx, vy = math.sin(theta), -math.cos(theta)
    cx, cy = center
    hw, hd = w / 2, d / 2
    return [
        (cx + sx * hw * ux + sz * hd * vx, cy + sx * hw * uy + sz * hd * vy)
        for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]


def rect_on_edge(a: Pt, u: Pt, n: Pt, t0: float, t1: float, depth: float) -> list[Pt]:
    p0 = (a[0] + u[0] * t0, a[1] + u[1] * t0)
    p1 = (a[0] + u[0] * t1, a[1] + u[1] * t1)
    return [
        p0,
        p1,
        (p1[0] + n[0] * depth, p1[1] + n[1] * depth),
        (p0[0] + n[0] * depth, p0[1] + n[1] * depth),
    ]


def polys_overlap(p: list[Pt], q: list[Pt], tol: float = 0.5) -> bool:
    """SAT pour polygones convexes ; un contact de moins de `tol` cm ne compte pas."""
    for poly in (p, q):
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            ax, ay = -(b[1] - a[1]), b[0] - a[0]
            norm = math.hypot(ax, ay)
            if norm < 1e-9:
                continue
            ax, ay = ax / norm, ay / norm
            pp = [x * ax + y * ay for x, y in p]
            qq = [x * ax + y * ay for x, y in q]
            if max(pp) - tol <= min(qq) or max(qq) - tol <= min(pp):
                return False
    return True


def subtract_intervals(base: tuple[float, float], cuts: list[tuple[float, float]]):
    free = [base]
    for c0, c1 in sorted(cuts):
        nxt = []
        for f0, f1 in free:
            if c1 <= f0 or c0 >= f1:
                nxt.append((f0, f1))
                continue
            if c0 > f0:
                nxt.append((f0, c0))
            if c1 < f1:
                nxt.append((c1, f1))
        free = nxt
    return [(round(a, 1), round(b, 1)) for a, b in free if b - a > 0.5]
