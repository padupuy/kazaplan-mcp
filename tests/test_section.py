import base64
import json
import struct
import xml.etree.ElementTree as ET

import numpy as np

from kazaplan_mcp import mesh, section, sketch

from .test_plan import fake_catalog  # noqa: F401
from .test_sketch import classes, furnished_plan


def box_glb(size=(2.0, 1.0, 1.0), translation=(5.0, 0.0, 0.0)) -> bytes:
    sx, sy, sz = size
    corners = np.array([(x, y, z) for x in (0, sx) for y in (0, sy) for z in (0, sz)], np.float32)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    idx = np.array([i for a, b, c, d in quads for i in (a, b, c, a, c, d)], np.uint16)
    binary = corners.tobytes() + idx.tobytes()
    gltf = {
        "asset": {"version": "2.0"},
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "translation": list(translation)}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [0.5, 0.4, 0.3, 1]}}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": corners.nbytes},
            {"buffer": 0, "byteOffset": corners.nbytes, "byteLength": idx.nbytes},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5123, "count": len(idx), "type": "SCALAR"},
        ],
    }
    text = json.dumps(gltf).encode()
    text += b" " * (-len(text) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunks = struct.pack("<II", len(text), 0x4E4F534A) + text
    chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<III", 0x46546C67, 2, 12 + len(chunks)) + chunks


def test_read_glb_applies_node_transform_and_material():
    tris, colors = mesh.read_glb(box_glb())
    assert tris.shape == (12, 3, 3)
    assert tris[..., 0].min() == 5 and tris[..., 0].max() == 7
    assert np.allclose(colors[0], (0.5, 0.4, 0.3))


def test_front_view_fills_the_footprint_with_outlined_shape():
    tris, colors = mesh.read_glb(box_glb())
    img = mesh.front_view(tris, colors, (100, 50, 40), (1, 0), (0, 1))
    assert img.size == (100 * mesh.PX_PER_CM, 50 * mesh.PX_PER_CM)
    px = np.asarray(img)
    assert (px[..., 3] > 0).mean() > 0.9
    assert (px[..., :3].sum(-1) < 300).any()


def test_drawing_is_cached_by_model_and_view(tmp_path, monkeypatch):
    monkeypatch.setattr(mesh, "ASSETS", tmp_path)
    monkeypatch.setattr(mesh, "RENDERS", tmp_path / "r")
    (tmp_path / "model-1.glb").write_bytes(box_glb())
    png = mesh.drawing("model-1", (100, 50, 40), (1.0, 0.0), (0.0, 1.0))
    assert base64.b64decode(png).startswith(b"\x89PNG")
    assert len(list((tmp_path / "r").glob("model-1-*.png"))) == 1
    assert mesh.drawing("model-404", (1, 1, 1), (1.0, 0.0), (0.0, 1.0)) is None


def test_section_faces_the_furnished_wall_with_its_openings(monkeypatch):
    plan = furnished_plan(monkeypatch)
    monkeypatch.setattr(mesh, "drawing", lambda *a: None)
    walls = section.section_walls(plan, "Salon")
    assert walls and all(not e.get("invisible") for e in walls)
    door_wall = next(e for e in plan.room_geometry("Salon")["edges"] if e["openings"])
    svg = section.render(plan, "Salon", door_wall, "1")
    ET.fromstring(svg)
    found = classes(svg)
    assert "back-wall" in found and door_wall["openings"][0]["kind"] in found
    assert "Coupe 1" in svg and ">4,00<" in svg


def test_model_view_turns_with_the_object():
    edge = {"from": [0, 0], "to": [400, 0], "inwardNormal": [0, 1]}
    frame = section._frame(edge)
    facing_wall = {"fp": {"theta": 0.0}}
    across, toward = section._model_view(facing_wall, frame)
    assert abs(across[0]) == 1 and across[1] == 0
    sideways = {"fp": {"theta": 1.5707963}}
    across, _ = section._model_view(sideways, frame)
    assert across[0] == 0 and abs(across[1]) == 1


def test_board_adds_sections_and_markers(monkeypatch):
    plan = furnished_plan(monkeypatch)
    monkeypatch.setattr(mesh, "drawing", lambda *a: None)
    decor = {"name": "Maison test", "rooms": {"salon": {"name": "Salon"}}}
    md, files = sketch.board(plan, decor)
    assert "![Coupe 1](plans/salon-coupe-1.svg)" in md
    assert files["plans/salon-coupe-1.svg"].startswith("<svg")
    assert "section-marker" in classes(files["plans/salon.svg"])
