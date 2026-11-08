import math

import pytest

from kazaplan_mcp import catalog, kzp
from kazaplan_mcp import geometry as g
from kazaplan_mcp.plan import Plan, PlanError

FLOOR = "floor-1"
ITEMS = {
    "model-1": {
        "id": "model-1",
        "kind": "model",
        "type": "prefab",
        "label": "Buffet",
        "w": 160,
        "d": 50,
        "h": 80,
        "elevation": 0,
    },
    "model-2": {
        "id": "model-2",
        "kind": "model",
        "type": "prefab",
        "label": "Table",
        "w": 100,
        "d": 100,
        "h": 75,
        "elevation": 0,
    },
    "material-1": {"id": "material-1", "kind": "material", "label": "Carrelage", "usage": ["floor"]},
}
TEMPLATE = [
    {
        "__name__": "model.model-structure",
        "position": {"x": 0, "y": 0, "z": 0},
        "rotation": {"x": 0, "y": 0, "z": 0},
        "boundings": {"dimensions": {"width": 160, "depth": 50, "height": 80}},
        "originCatalogId": "model-1",
        "trackerData": {},
        "initParams": {},
    }
]


@pytest.fixture(autouse=True)
def fake_catalog(monkeypatch):
    monkeypatch.setattr(catalog, "get", ITEMS.get)
    monkeypatch.setattr(
        catalog,
        "templates",
        lambda: {
            "model-1": TEMPLATE,
            "model-2": [
                {
                    **TEMPLATE[0],
                    "originCatalogId": "model-2",
                    "boundings": {"dimensions": {"width": 100, "depth": 100, "height": 75}},
                }
            ],
        },
    )


def make_plan() -> Plan:
    project = {
        "__name__": "wnp/project",
        "id": "p",
        "title": "Test",
        "layers": {
            "floors": [
                {
                    "__name__": "floor",
                    "id": FLOOR,
                    "index": 0,
                    "referenceHeight": 0,
                    "ceilingHeight": 250,
                    "slabThickness": 20,
                }
            ],
            "floorHistory": [{"__name__": "floorHistory", "currentFloorId": FLOOR}],
            "catalog": [],
            FLOOR: [],
        },
    }
    plan = Plan({"version": "test"}, project)
    plan.add_walls([[-10, -10], [410, -10], [410, 310], [-10, 310]], thickness=20, closed=True)
    plan.objects.append(
        {
            "__name__": "wall.room",
            "id": "room-1",
            "type": "livingdiningRoom",
            "customName": "Salon",
            "elevation": 0,
            "path": [[{"x": x, "y": y} for x, y in [(0, 0), (400, 0), (400, 300), (0, 300)]]],
            "paneIds": [],
            "materials": {},
        }
    )
    plan.geometry_dirty = False
    return plan


def wall_along(plan, a, b):
    for w in plan.of_type("wall.wall"):
        ext = [(e["position"]["x"], e["position"]["y"]) for e in w["connectionExtremities"]]
        if ext == [a, b]:
            return w["id"]
    raise AssertionError


def test_kzp_roundtrip():
    plan = make_plan()
    plan2 = Plan.from_bytes(plan.to_bytes())
    assert plan2.project["layers"][FLOOR] == plan.objects
    assert kzp.read_header(plan.to_bytes())["magic"] == "WPRJ"


def test_opening_uses_negated_z_and_wall_angle():
    plan = make_plan()
    wid = wall_along(plan, (410, -10), (410, 310))
    oid = plan.add_opening(wid, "door", offset=100)
    door = plan.get(oid)
    assert door["position"]["x"] == pytest.approx(410)
    assert door["position"]["z"] == pytest.approx(-(-10 + 100 + 45))
    assert door["rotation"]["y"] == pytest.approx(math.pi / 2)
    assert plan.geometry_dirty


def test_room_geometry_free_segments():
    plan = make_plan()
    wid = wall_along(plan, (-10, -10), (410, -10))
    plan.add_opening(wid, "door", offset=110, width=90)
    geo = plan.room_geometry("salon")
    bottom = next(e for e in geo["edges"] if e["from"] == [0, 0] and e["to"] == [400, 0])
    assert bottom["wallId"] == wid
    assert bottom["openings"][0]["from"] == pytest.approx(100)
    assert bottom["free"] == [(0, 95), (195, 400)]
    assert geo["area_m2"] == 12


def test_place_against_wall_back_flush_and_facing_room():
    plan = make_plan()
    res = plan.place("model-1", "Salon", against_wall=0, offset=20)
    fp = plan.footprint(plan.get(res["ids"][0]))
    ys = [p[1] for p in fp["poly"]]
    assert min(ys) == pytest.approx(1)
    assert max(ys) == pytest.approx(51)
    front = (-math.sin(fp["theta"]), math.cos(fp["theta"]))
    assert front == pytest.approx((0, 1), abs=1e-9)
    assert plan.get(res["ids"][0]).get("trackerData") is None


def test_place_avoids_existing_objects_and_door_swing():
    plan = make_plan()
    wid = wall_along(plan, (-10, -10), (410, -10))
    plan.add_opening(wid, "door", offset=110, width=90)
    first = plan.place("model-1", "Salon", against_wall=0)
    with pytest.raises(PlanError, match="chevauche"):
        plan.place("model-1", "Salon", against_wall=0)
    second = plan.place("model-1", "Salon")
    p1 = plan.footprint(plan.get(first["ids"][0]))["poly"]
    p2 = plan.footprint(plan.get(second["ids"][0]))["poly"]
    assert not g.polys_overlap(p1, p2)
    with pytest.raises(PlanError, match="débattement"):
        plan.place("model-2", "Salon", x=150, y=60)


def test_place_rejects_out_of_room_unless_forced():
    plan = make_plan()
    with pytest.raises(PlanError, match="dépasse"):
        plan.place("model-2", "Salon", x=20, y=20)
    res = plan.place("model-2", "Salon", x=20, y=20, force=True)
    assert res["warnings"]


def test_remove_wall_cascades_openings():
    plan = make_plan()
    wid = wall_along(plan, (-10, -10), (410, -10))
    oid = plan.add_opening(wid, "casement-window")
    removed = plan.remove(wid)
    assert set(removed) == {wid, oid}
    neighbours = [e for w in plan.of_type("wall.wall") for e in w["connectionExtremities"]]
    assert all(e["wallId"] != wid for e in neighbours)


def test_save_keeps_panes_even_after_geometry_change():
    plan = make_plan()
    plan.objects.append({"__name__": "wall.pane", "id": "pane-1"})
    plan.geometry_dirty = True
    assert any(o["__name__"] == "wall.pane" for o in Plan.from_bytes(plan.to_bytes()).objects)


def test_set_floor_material_tracks_catalog():
    plan = make_plan()
    plan.set_material("floor:salon", "material-1")
    assert plan.room("Salon")["materials"]["flooring"] == "catalog:material-1"
    assert "material-1" in plan.project["layers"]["catalog"][0]["itemDiff"]


def test_place_ignores_absolute_template_height(monkeypatch):
    sunk = [{**TEMPLATE[0], "position": {"x": 0, "y": -40, "z": 0}}]
    monkeypatch.setattr(catalog, "templates", lambda: {"model-1": sunk})
    plan = make_plan()
    res = plan.place("model-1", "Salon", against_wall=0)
    assert plan.get(res["ids"][0])["position"]["y"] == 0


def test_place_resized_sets_mesh_scaling():
    plan = make_plan()
    res = plan.place("model-1", "Salon", against_wall=0, offset=10, width=320, depth=50)
    obj = plan.get(res["ids"][0])
    assert obj["meshScaling"]["x"] == pytest.approx(2)
    assert plan.footprint(obj)["w"] == pytest.approx(320)


def test_place_under_opening_centers_on_window():
    plan = make_plan()
    wid = wall_along(plan, (-10, -10), (410, -10))
    oid = plan.add_opening(wid, "casement-window", offset=200, width=100)
    res = plan.place("model-1", "Salon", under_opening=oid, height=60)
    assert res["x"] == pytest.approx(240)


def test_place_outdoor_rejects_wall_crossing():
    plan = make_plan()
    res = plan.place("model-2", None, x=600, y=150)
    assert plan.get(res["ids"][0])["position"]["y"] == 0
    with pytest.raises(PlanError, match="traverse le mur"):
        plan.place("model-2", None, x=430, y=150)


def test_no_collision_models_may_overlap(monkeypatch):
    door = {**ITEMS["model-1"], "id": "model-3", "d": 2, "magnetism": ["NO_COLLISION"]}
    monkeypatch.setattr(catalog, "get", {**ITEMS, "model-3": door}.get)
    monkeypatch.setattr(catalog, "templates", lambda: {"model-1": TEMPLATE, "model-3": TEMPLATE})
    plan = make_plan()
    plan.place("model-1", "Salon", against_wall=0, offset=20)
    res = plan.place("model-3", "Salon", against_wall=0, offset=20, gap=40)
    assert res["warnings"] == []
    assert res["y"] == pytest.approx(41)


def test_save_prunes_dangling_pane_references():
    plan = make_plan()
    wall = plan.of_type("wall.wall")[0]
    room = plan.room("Salon")
    plan.objects.append({"__name__": "wall.pane", "id": "pane-ok"})
    plan.objects.append({"__name__": "baseboard.baseboard-structure", "id": "bb-ok", "paneId": "pane-ok"})
    plan.objects.append({"__name__": "baseboard.baseboard-structure", "id": "bb-gone", "paneId": "pane-gone"})
    wall["paneIds"] = {"pane-ok": True, "pane-gone": True}
    room["paneIds"] = ["pane-ok", "pane-gone"]

    saved = Plan.from_bytes(plan.to_bytes())
    assert saved.get(wall["id"])["paneIds"] == {"pane-ok": True}
    assert saved.room("Salon")["paneIds"] == ["pane-ok"]
    assert {o["id"] for o in saved.of_type("baseboard.baseboard-structure")} == {"bb-ok"}


def test_set_room_renames_but_never_creates():
    plan = make_plan()
    rid = plan.set_room("Salon", type="garage", name="Garage")
    assert plan.get(rid)["type"] == "garage"
    assert plan.room_label(plan.get(rid)) == "Garage"
    with pytest.raises(PlanError, match="Type de pièce inconnu"):
        plan.set_room("Garage", type="poolhouse")
    with pytest.raises(TypeError):
        plan.set_room(type="garage", path=[[0, 0], [1, 0], [1, 1]])


def add_panes(plan):
    room = plan.room("Salon")
    for i, w in enumerate(plan.of_type("wall.wall")):
        plan.objects.append(
            {
                "__name__": "wall.pane",
                "id": f"pane-in-{i}",
                "roomInfo": {"id": room["id"]},
                "wallInfo": {"id": w["id"], "edgeIndex": 1},
                "materials": {},
            }
        )
        plan.objects.append(
            {
                "__name__": "wall.pane",
                "id": f"pane-out-{i}",
                "roomInfo": {"id": None},
                "wallInfo": {"id": w["id"], "edgeIndex": 3},
                "materials": {},
            }
        )


def test_paint_all_room_walls_but_not_outside_faces(monkeypatch):
    paint = {"id": "material-9", "kind": "material", "label": "Peinture", "usage": ["wall"]}
    monkeypatch.setattr(catalog, "get", {**ITEMS, "material-9": paint}.get)
    plan = make_plan()
    add_panes(plan)
    res = plan.set_material("wall:salon", "material-9")
    assert res["panes"] == 4 and res["warnings"] == []
    inside = [p for p in plan.of_type("wall.pane") if p["id"].startswith("pane-in")]
    outside = [p for p in plan.of_type("wall.pane") if p["id"].startswith("pane-out")]
    assert all(p["materials"] == {"wall.pane": "catalog:material-9"} for p in inside)
    assert all(p["materials"] == {} for p in outside)


def test_paint_one_wall_by_edge_index():
    plan = make_plan()
    add_panes(plan)
    wid = wall_along(plan, (-10, -10), (410, -10))
    geo = plan.room_geometry("Salon")
    edge = next(e["index"] for e in geo["edges"] if e["wallId"] == wid)
    res = plan.set_material(f"wall:Salon:{edge}", "material-1")
    painted = [p for p in plan.of_type("wall.pane") if p["materials"]]
    assert [p["wallInfo"]["id"] for p in painted] == [wid]
    assert res["warnings"]


def test_paint_requires_panes():
    plan = make_plan()
    with pytest.raises(PlanError, match="Aucune face"):
        plan.set_material("wall:salon", "material-1")


def test_ground_material():
    plan = make_plan()
    plan.project["layers"]["ground"] = [{"__name__": "ground", "id": "g", "materials": {}}]
    plan.set_material("ground", "material-1")
    assert plan.project["layers"]["ground"][0]["materials"] == {"ground": "catalog:material-1"}


def test_place_with_elevation_and_on_top_of(monkeypatch):
    lamp = {**ITEMS["model-2"], "id": "model-4", "w": 20, "d": 20, "h": 40}
    monkeypatch.setattr(catalog, "get", {**ITEMS, "model-4": lamp}.get)
    monkeypatch.setattr(catalog, "templates", lambda: {"model-1": TEMPLATE, "model-4": TEMPLATE})
    plan = make_plan()
    buffet = plan.place("model-1", "Salon", against_wall=0, offset=100)
    on = plan.place("model-4", None, on_top_of=buffet["ids"][0])
    assert on["room"] == "Salon"
    assert on["elevation"] == pytest.approx(80)
    assert (on["x"], on["y"]) == (buffet["x"], buffet["y"])
    mirror = plan.place("model-4", "Salon", against_wall=2, elevation=120)
    assert plan.get(mirror["ids"][0])["position"]["y"] == pytest.approx(120)


def test_on_top_of_with_elevation_sets_surface_height(monkeypatch):
    cushion = {**ITEMS["model-2"], "id": "model-4", "w": 45, "d": 45, "h": 10}
    monkeypatch.setattr(catalog, "get", {**ITEMS, "model-4": cushion}.get)
    monkeypatch.setattr(catalog, "templates", lambda: {"model-1": TEMPLATE, "model-4": TEMPLATE})
    plan = make_plan()
    bed = plan.place("model-1", "Salon", against_wall=0, offset=100)
    on = plan.place("model-4", None, on_top_of=bed["ids"][0], elevation=52)
    assert on["room"] == "Salon"
    assert on["elevation"] == pytest.approx(52)


def test_partition_tees_into_existing_wall():
    plan = make_plan()
    host = wall_along(plan, (-10, -10), (410, -10))
    (wid,) = plan.add_walls([[200, -10], [200, 310]], thickness=7)
    start, end = plan.get(wid)["connectionExtremities"]
    assert start["wallId"] == host and start["strong"] is False
    assert start["targetEdgeIndex"] == 1
    assert (start["position"]["x"], start["position"]["y"]) == pytest.approx((200, 0))
    assert end["wallId"] is not None and end["targetEdgeIndex"] == 1
    assert end["position"]["y"] == pytest.approx(300)


def test_wall_joins_free_end_as_corner():
    plan = make_plan()
    (a,) = plan.add_walls([[600, 0], [800, 0]], thickness=20)
    (b,) = plan.add_walls([[800, 2], [800, 200]], thickness=20)
    assert plan.get(b)["connectionExtremities"][0] | {"position": None} == {
        "position": None,
        "wallId": a,
        "targetEdgeIndex": -1,
        "strong": True,
    }
    assert plan.get(a)["connectionExtremities"][1]["wallId"] == b


def test_free_standing_walls_stay_unattached():
    plan = make_plan()
    ids = plan.add_walls([[600, 0], [800, 0], [800, 200]], thickness=20)
    exts = [e for i in ids for e in plan.get(i)["connectionExtremities"]]
    assert exts[0]["wallId"] is None and exts[-1]["wallId"] is None


def test_partition_on_the_other_face_uses_edge_three():
    plan = make_plan()
    host = wall_along(plan, (-10, -10), (410, -10))
    (wid,) = plan.add_walls([[200, -10], [200, -200]], thickness=7)
    start = plan.get(wid)["connectionExtremities"][0]
    assert (start["wallId"], start["targetEdgeIndex"]) == (host, 3)
    assert start["position"]["y"] == pytest.approx(-20)


def test_invisible_separation_is_skipped():
    plan = make_plan()
    add_panes(plan)
    wid = wall_along(plan, (-10, -10), (410, -10))
    plan.get(wid)["wallRenderer"] = {"__name__": "wall.invisible-renderer"}
    res = plan.set_material("wall:salon", "material-1")
    assert res["panes"] == 3
    edge = next(e for e in plan.room_geometry("Salon")["edges"] if e["wallId"] == wid)
    assert edge["invisible"] and edge["free"] == []
    with pytest.raises(PlanError, match="visible"):
        plan.set_material(f"wall:salon:{edge['index']}", "material-1")
    assert plan.place("model-2", None, x=200, y=-10, force=False)["warnings"] == []


def test_ceiling_material(monkeypatch):
    paint = {"id": "material-9", "kind": "material", "label": "Peinture", "usage": ["wall"]}
    monkeypatch.setattr(catalog, "get", {**ITEMS, "material-9": paint}.get)
    plan = make_plan()
    res = plan.set_material("ceiling:salon", "material-9")
    assert plan.room("Salon")["materials"]["ceil"] == "catalog:material-9"
    assert res["ceiling"] == "material-9" and res["warnings"] == []


def test_ceiling_material_requires_a_ceiling():
    plan = make_plan()
    plan.room("Salon")["ceiling"] = False
    with pytest.raises(PlanError, match="sans plafond"):
        plan.set_material("ceiling:salon", "material-1")


def test_move_carries_objects_on_top_and_checks_collisions(monkeypatch):
    lamp = {**ITEMS["model-2"], "id": "model-4", "w": 20, "d": 20, "h": 40}
    monkeypatch.setattr(catalog, "get", {**ITEMS, "model-4": lamp}.get)
    monkeypatch.setattr(catalog, "templates", lambda: {"model-1": TEMPLATE, "model-4": TEMPLATE})
    plan = make_plan()
    buffet = plan.place("model-1", "Salon", x=200, y=150, rotation=0)
    on = plan.place("model-4", None, on_top_of=buffet["ids"][0])
    res = plan.move(buffet["ids"][0], dx=30, dy=-20)
    assert set(res["moved"]) == {buffet["ids"][0], on["ids"][0]}
    lamp_fp = plan.footprint(plan.get(on["ids"][0]))
    assert lamp_fp["center"] == pytest.approx((230, 130))
    assert lamp_fp["y0"] == pytest.approx(80)
    with pytest.raises(PlanError, match="Déplacement refusé"):
        plan.move(buffet["ids"][0], dx=300)
    assert plan.footprint(plan.get(buffet["ids"][0]))["center"] == pytest.approx((230, 130))


def test_rugs_are_not_obstacles_and_do_not_carry_furniture(monkeypatch):
    rug = {**ITEMS["model-2"], "id": "model-5", "w": 200, "d": 140, "h": 1}
    monkeypatch.setattr(catalog, "get", {**ITEMS, "model-5": rug}.get)
    templates = {
        "model-1": TEMPLATE,
        "model-5": [
            {
                **TEMPLATE[0],
                "originCatalogId": "model-5",
                "boundings": {"dimensions": {"width": 200, "depth": 140, "height": 1}},
            }
        ],
    }
    monkeypatch.setattr(catalog, "templates", lambda: templates)
    plan = make_plan()
    carpet = plan.place("model-5", "Salon", x=200, y=150, force=True)
    buffet = plan.place("model-1", "Salon", x=200, y=150, rotation=0)
    assert buffet["warnings"] == []
    assert plan.move(buffet["ids"][0], dx=20)["warnings"] == []
    assert plan.move(carpet["ids"][0], dy=10)["moved"] == carpet["ids"]
