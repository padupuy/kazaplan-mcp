"""Modèles 3D du catalogue (.glb) vus de face : lecture glTF minimale et rendu au trait en PNG."""

import base64
import io
import json
import math
import struct

import httpx
import numpy as np
from PIL import Image, ImageDraw

from . import catalog

CDN = "https://cdn.kazaplan.com"
ASSETS = catalog.CACHE / "assets"
RENDERS = catalog.CACHE / "elevations"
PX_PER_CM = 2
SUPERSAMPLE = 2
CREASE = math.cos(math.radians(28))
DEPTH_STEP = 2.0
INK = (47, 43, 39)

COMPONENTS = {
    5120: np.int8,
    5121: np.uint8,
    5122: np.int16,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _accessor(gltf, binary, index):
    acc = gltf["accessors"][index]
    view = gltf["bufferViews"][acc["bufferView"]]
    dtype = np.dtype(COMPONENTS[acc["componentType"]])
    width = WIDTHS[acc["type"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride") or dtype.itemsize * width
    raw = np.frombuffer(
        binary, np.uint8, count=stride * (acc["count"] - 1) + dtype.itemsize * width, offset=start
    )
    rows = np.lib.stride_tricks.as_strided(raw, (acc["count"], dtype.itemsize * width), (stride, 1))
    return np.ascontiguousarray(rows).view(dtype).reshape(acc["count"], width)


def _local_matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"], float).reshape(4, 4).T
    x, y, z, w = node.get("rotation", (0, 0, 0, 1))
    rot = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    m = np.eye(4)
    m[:3, :3] = rot * np.array(node.get("scale", (1, 1, 1)))
    m[:3, 3] = node.get("translation", (0, 0, 0))
    return m


def read_glb(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Triangles (N, 3, 3) dans le repère du modèle et couleur de base de chacun (N, 3), 0-1."""
    json_len = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20 : 20 + json_len])
    binary = data[28 + json_len :] if len(data) > 20 + json_len else b""
    materials = gltf.get("materials", [])
    tris, colors = [], []

    def visit(i, parent):
        node = gltf["nodes"][i]
        m = parent @ _local_matrix(node)
        for prim in gltf["meshes"][node["mesh"]]["primitives"] if "mesh" in node else []:
            if prim.get("mode", 4) != 4 or "POSITION" not in prim["attributes"]:
                continue
            pos = _accessor(gltf, binary, prim["attributes"]["POSITION"]).astype(float)
            pos = pos @ m[:3, :3].T + m[:3, 3]
            idx = (
                _accessor(gltf, binary, prim["indices"]).ravel().astype(np.int64)
                if "indices" in prim
                else np.arange(len(pos))
            )
            t = pos[idx[: len(idx) // 3 * 3]].reshape(-1, 3, 3)
            mat = materials[prim["material"]] if "material" in prim else {}
            base = (mat.get("pbrMetallicRoughness") or {}).get("baseColorFactor", (0.9, 0.9, 0.9, 1))
            tris.append(t)
            colors.append(np.tile(base[:3], (len(t), 1)))
        for c in node.get("children", []):
            visit(c, m)

    scene = (
        gltf["scenes"][gltf.get("scene", 0)] if gltf.get("scenes") else {"nodes": range(len(gltf["nodes"]))}
    )
    for i in scene["nodes"]:
        visit(i, np.eye(4))
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3))
    return np.concatenate(tris), np.concatenate(colors)


def asset(model_id: str) -> bytes | None:
    """Le .glb d'un modèle, téléchargé une fois dans cache/assets/ ; None si le catalogue n'en a pas."""
    path = ASSETS / f"{model_id}.glb"
    if path.exists():
        return path.read_bytes()
    item = catalog.get(model_id)
    ref = (item or {}).get("_asset3d")
    if not ref:
        return None
    try:
        r = httpx.get(CDN + ref.removeprefix("cdn:"), timeout=30, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    ASSETS.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return r.content


def front_view(tris, colors, size, across, toward) -> Image.Image:
    """Vue orthogonale du modèle mis aux dimensions size = (largeur, hauteur, profondeur) en cm.
    across = (a, b) : abscisse écran = a·x + b·z ; toward = (c, e) : éloignement = c·x + e·z
    (x, z : axes du modèle, centrés)."""
    w, h, d = size
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    span = np.where(hi - lo > 1e-6, hi - lo, 1)
    p = (tris - (lo + hi) / 2) / span * np.array([w, h, d])
    x, y, z = p[..., 0], p[..., 1] + h / 2, p[..., 2]
    s = across[0] * x + across[1] * z
    t = toward[0] * x + toward[1] * z

    k = PX_PER_CM * SUPERSAMPLE
    s0, width = s.min(), max(s.max() - s.min(), 1)
    size_px = (max(1, math.ceil(width * k)), max(1, math.ceil(h * k)))
    sx, sy = (s - s0) * k, (h - y) * k

    e1 = np.stack([s[:, 1] - s[:, 0], y[:, 1] - y[:, 0], t[:, 1] - t[:, 0]], -1)
    e2 = np.stack([s[:, 2] - s[:, 0], y[:, 2] - y[:, 0], t[:, 2] - t[:, 0]], -1)
    n = np.cross(e1, e2)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    n[n[:, 2] > 0] *= -1  # face tournée vers l'observateur (t décroissant)
    light = np.array([-0.35, 0.55, -0.75])
    light /= np.linalg.norm(light)
    shade = 0.72 + 0.28 * np.clip(n @ light, 0, 1)
    tint = 0.7 + 0.3 * colors
    rgb = np.clip(tint * shade[:, None] * 255, 0, 255).astype(int)

    color = Image.new("RGBA", size_px, (0, 0, 0, 0))
    normal = Image.new("RGB", size_px, (0, 0, 0))
    depth = Image.new("I", size_px, 0)
    dc, dn, dd = ImageDraw.Draw(color), ImageDraw.Draw(normal), ImageDraw.Draw(depth)
    order = np.argsort(-t.mean(1))
    nq = ((n + 1) * 127.5).astype(int)
    tq = ((t.mean(1) - t.min() + 1) * 10).astype(int)
    for i in order:
        poly = list(zip(sx[i].tolist(), sy[i].tolist(), strict=True))
        dc.polygon(poly, fill=(*rgb[i], 255))
        dn.polygon(poly, fill=tuple(nq[i]))
        dd.polygon(poly, fill=int(tq[i]))

    rgba = np.asarray(color).astype(float)
    nv = np.asarray(normal).astype(float) / 127.5 - 1
    dv = np.asarray(depth).astype(float) / 10
    alpha = rgba[..., 3] > 0
    edge = np.zeros(alpha.shape, bool)
    for axis in (0, 1):
        same = (nv * np.roll(nv, 1, axis)).sum(-1) / (
            np.linalg.norm(nv, axis=-1) * np.linalg.norm(np.roll(nv, 1, axis), axis=-1) + 1e-9
        )
        jump = np.abs(dv - np.roll(dv, 1, axis)) > DEPTH_STEP
        border = alpha != np.roll(alpha, 1, axis)
        edge |= ((same < CREASE) | jump) & alpha & np.roll(alpha, 1, axis) | border
    edge[0, :], edge[:, 0] = alpha[0, :], alpha[:, 0]
    edge[-1, :] |= alpha[-1, :]
    edge[:, -1] |= alpha[:, -1]
    rgba[edge] = (*INK, 255)
    img = Image.fromarray(rgba.astype(np.uint8), "RGBA")
    return img.resize((max(1, size_px[0] // SUPERSAMPLE), max(1, size_px[1] // SUPERSAMPLE)), Image.LANCZOS)


def drawing(model_id: str, size, across, toward) -> str | None:
    """PNG base64 de la vue de face, mis en cache par modèle, dimensions et angle de vue."""
    key = (
        f"{model_id}-{round(size[0])}x{round(size[1])}x{round(size[2])}-"
        f"{across[0]:+.2f}{across[1]:+.2f}{toward[0]:+.2f}{toward[1]:+.2f}"
    )
    path = RENDERS / f"{key}.png"
    if not path.exists():
        data = asset(model_id)
        if not data:
            return None
        try:
            tris, colors = read_glb(data)
        except (KeyError, ValueError, struct.error):
            return None
        if not len(tris):
            return None
        buf = io.BytesIO()
        front_view(tris, colors, size, across, toward).save(buf, "PNG", optimize=True)
        RENDERS.mkdir(parents=True, exist_ok=True)
        path.write_bytes(buf.getvalue())
    return base64.b64encode(path.read_bytes()).decode()
