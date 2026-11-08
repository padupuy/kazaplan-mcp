import xml.etree.ElementTree as ET

import pytest

from kazaplan_mcp import catalog, sketch

from .test_plan import ITEMS, TEMPLATE, fake_catalog, make_plan, wall_along  # noqa: F401

RUG = {**ITEMS["model-2"], "id": "model-5", "label": "Tapis", "w": 200, "d": 140, "h": 1}
LIGHT = {**ITEMS["model-2"], "id": "model-6", "label": "Suspension", "w": 40, "d": 40, "h": 100}
MIRROR = {**ITEMS["model-2"], "id": "model-7", "label": "Miroir", "w": 90, "d": 2, "h": 70}
PAINT = {"id": "material-9", "kind": "material", "label": "PAPER 5", "usage": ["wall"]}


def furnished_plan(monkeypatch):
    items = {**ITEMS, "model-5": RUG, "model-6": LIGHT, "model-7": MIRROR, "material-9": PAINT}
    monkeypatch.setattr(catalog, "get", items.get)
    templates = {
        k: [
            {
                **TEMPLATE[0],
                "originCatalogId": k,
                "boundings": {"dimensions": {"width": it["w"], "depth": it["d"], "height": it["h"]}},
            }
        ]
        for k, it in items.items()
        if k.startswith("model")
    }
    monkeypatch.setattr(catalog, "templates", lambda: templates)
    plan = make_plan()
    plan.add_opening(wall_along(plan, (-10, -10), (410, -10)), "door", offset=110, width=90)
    plan.add_opening(wall_along(plan, (410, 310), (-10, 310)), "casement-window", offset=200, width=100)
    plan.place("model-1", "Salon", against_wall=2, offset=100)
    plan.place("model-5", "Salon", x=200, y=150, force=True)
    plan.place("model-6", "Salon", x=200, y=150, elevation=150, force=True)
    plan.place("model-7", "Salon", against_wall=1, elevation=120)
    return plan


def classes(svg):
    root = ET.fromstring(svg)
    return [el.get("class") for el in root.iter() if el.get("class")]


def test_room_svg_draws_walls_openings_furniture_and_lights(monkeypatch):
    out = sketch.render(furnished_plan(monkeypatch), "Salon")
    found = classes(out["svg"])
    for kind in ("floor", "wall", "door", "window", "rug", "furniture", "light", "wall-item"):
        assert kind in found, kind
    assert ">A</text>" in out["svg"]
    assert any(line.startswith("A  Buffet (160 × 50)") for line in out["legend"])
    assert out["wall"] == ["Miroir (90 × 70, à 120 cm)"]
    assert out["ceiling"] == ["Suspension"]


def test_painted_walls_use_the_palette_color(monkeypatch):
    plan = furnished_plan(monkeypatch)
    plan.objects.append(
        {
            "__name__": "wall.pane",
            "id": "pane-1",
            "roomInfo": {"id": "room-1"},
            "wallInfo": {"id": wall_along(plan, (-10, -10), (410, -10))},
            "materials": {"wall.pane": "catalog:material-9"},
        }
    )
    svg = sketch.render(plan, "Salon", paint_hex={"material-9": "#ede6de"})["svg"]
    assert 'class="paint"' in svg and 'stroke="#ede6de"' in svg


def test_lamp_on_furniture_is_not_a_wall_item(monkeypatch):
    plan = furnished_plan(monkeypatch)
    buffet = next(o for o in plan.of_type("model.model-structure") if o["originCatalogId"] == "model-1")
    plan.place("model-7", None, on_top_of=buffet["id"])
    out = sketch.render(plan, "Salon")
    assert out["wall"] == ["Miroir (90 × 70, à 120 cm)"]
    assert out["on_top"] == ["Miroir (à 80 cm)"]


def test_label_comes_from_the_placed_variant(monkeypatch):
    plan = furnished_plan(monkeypatch)
    buffet = next(o for o in plan.of_type("model.model-structure") if o["originCatalogId"] == "model-1")
    buffet["catalogId"] = "model-2"
    assert any(line.startswith("A  Buffet") for line in sketch.render(plan, "Salon")["legend"])


def test_house_view_labels_rooms_without_legend(monkeypatch):
    out = sketch.render(furnished_plan(monkeypatch))
    assert out["legend"] == [] and ">Salon</text>" in out["svg"]
    assert ">A</text>" not in out["svg"]


def test_board_has_global_view_palette_and_room_sections(monkeypatch):
    decor = {
        "name": "Maison test",
        "colors": {"primary": "#ede6de", "accent": "#2f5d53"},
        "paints": {"primary": "material-9"},
        "rooms": {
            "salon": {
                "name": "Salon",
                "uses": ["lire"],
                "walls": "{colors.primary}",
                "accent": {"color": "{colors.accent}", "wall": "tête de lit"},
            }
        },
    }
    md, files = sketch.board(furnished_plan(monkeypatch), decor)
    assert md.startswith("# Maison test")
    assert "## Vue d'ensemble" in md and "## 01 · Salon" in md
    assert "[Salon](#01--salon)" in md
    assert "![Vue d'ensemble](plans/maison.svg)" in md and "![Salon](plans/salon.svg)" in md
    assert "![primary](swatches/primary.svg)" in md and "`#2f5d53`" in md
    assert "| Accent — tête de lit |" in md and "**PAPER 5**" in md
    assert "| **A** | Buffet | 1 | 160 × 50 | au sol |" in md
    assert "| · | Miroir | 1 | 90 × 70 | au mur, à 120 cm |" in md
    assert 'fill="#2f5d53"' in files["swatches/accent.svg"]
    assert "PAPER 5" in files["swatches/palette.svg"]
    assert files["plans/salon.svg"].startswith("<svg")


def test_plan_source_picks_latest_backup_for_an_id(tmp_path, monkeypatch):
    monkeypatch.setattr(sketch.api, "BACKUPS", tmp_path)
    (tmp_path / "123-20261015-100000-orig.kzp").write_bytes(b"old")
    (tmp_path / "123-20261016-100000-sent.kzp").write_bytes(b"new")
    (tmp_path / "999-20261017-100000-sent.kzp").write_bytes(b"other")
    (tmp_path / "123-cuisine-rebased.kzp").write_bytes(b"manual")
    assert sketch.plan_source("123").name == "123-20261016-100000-sent.kzp"
    assert sketch.plan_source(str(tmp_path / "x.kzp")) == tmp_path / "x.kzp"


DECOR_YAML = """---
name: Maison test
colors:
  primary: "#ede6de"
  "../../evil": "#000000"
rooms:
  salon:
    name: Salon
---
"""


def test_write_board_stays_next_to_decor(monkeypatch, tmp_path):
    decor = tmp_path / "maison" / "DECOR.md"
    decor.parent.mkdir()
    decor.write_text(DECOR_YAML.replace('  "../../evil": "#000000"\n', ""))
    out = sketch.write_board(furnished_plan(monkeypatch), decor)
    assert "PLANCHES.md" in out["files"] and "plans/salon.svg" in out["files"]
    assert (decor.parent / "PLANCHES.md").read_text().startswith("# Maison test")


def test_write_board_refuses_paths_outside_decor_dir(monkeypatch, tmp_path):
    decor = tmp_path / "maison" / "DECOR.md"
    decor.parent.mkdir()
    decor.write_text(DECOR_YAML)
    with pytest.raises(ValueError, match="refusé"):
        sketch.write_board(furnished_plan(monkeypatch), decor)
    assert not (tmp_path / "evil.svg").exists()


def test_write_board_requires_a_decor_file(monkeypatch, tmp_path):
    (tmp_path / "notes.md").write_text(DECOR_YAML)
    with pytest.raises(ValueError, match="DECOR.md"):
        sketch.write_board(furnished_plan(monkeypatch), tmp_path / "notes.md")
