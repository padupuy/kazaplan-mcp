from kazaplan_mcp import catalog, circulation

from .test_plan import ITEMS, TEMPLATE, fake_catalog, make_plan, wall_along  # noqa: F401

MODELS = {
    "model-1": {**ITEMS["model-1"], "menuCodes": ["M_BUFFETS"]},
    "model-10": {
        **ITEMS["model-2"],
        "id": "model-10",
        "label": "Chaise",
        "w": 44,
        "d": 50,
        "h": 85,
        "menuCodes": ["M_CHAISES"],
    },
    "model-11": {
        **ITEMS["model-2"],
        "id": "model-11",
        "label": "Canapé",
        "w": 200,
        "d": 90,
        "h": 80,
        "menuCodes": ["M_CANAPES"],
    },
    "model-12": {
        **ITEMS["model-2"],
        "id": "model-12",
        "label": "Table basse",
        "w": 100,
        "d": 60,
        "h": 40,
        "menuCodes": ["M_TABLES"],
    },
    "model-13": {
        **ITEMS["model-2"],
        "id": "model-13",
        "label": "Table à manger",
        "w": 160,
        "d": 90,
        "h": 75,
        "menuCodes": ["M_TABLES"],
    },
}


def room_plan(monkeypatch):
    items = {**ITEMS, **MODELS}
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
    plan.add_opening(
        wall_along(plan, (410, 310), (-10, 310)),
        "casement-window",
        offset=200,
        width=100,
        height=215,
        elevation=0,
    )
    return plan


def issues(report, side=None):
    return [c for c in report["clearances"] if not c["ok"] and (side is None or c["side"] == side)]


def test_empty_room_paths_are_comfortable(monkeypatch):
    report = circulation.check(room_plan(monkeypatch), "Salon")
    assert report["paths"] and all(p["width90"] for p in report["paths"])
    assert issues(report) == []


def test_furniture_in_front_of_french_window_blocks_the_path(monkeypatch):
    plan = room_plan(monkeypatch)
    plan.place("model-1", "Salon", x=160, y=270, rotation=180, force=True)
    plan.place("model-1", "Salon", x=160, y=225, rotation=180, force=True)
    paths = circulation.check(plan, "Salon")["paths"]
    assert any(not p["width60"] for p in paths)


def test_chair_needs_room_behind(monkeypatch):
    plan = room_plan(monkeypatch)
    plan.place("model-13", "Salon", x=300, y=120, rotation=0, force=True)
    plan.place("model-10", "Salon", x=320, y=40, rotation=0, force=True)
    found = [c for c in issues(circulation.check(plan, "Salon"), "derrière") if c["label"] == "Chaise"]
    assert found and found[0]["free_cm"] < 75 and found[0]["min_cm"] == 75


def test_sofa_needs_60_before_the_coffee_table(monkeypatch):
    plan = room_plan(monkeypatch)
    plan.place("model-11", "Salon", x=200, y=150, rotation=0, force=True)
    plan.place("model-12", "Salon", x=200, y=240, rotation=0, force=True)
    found = issues(circulation.check(plan, "Salon"), "devant")
    assert [c["label"] for c in found] == ["Canapé"]
    assert 10 <= found[0]["free_cm"] <= 20


def test_dining_table_needs_110_around_ignoring_chairs(monkeypatch):
    plan = room_plan(monkeypatch)
    plan.place("model-13", "Salon", x=200, y=150, rotation=0, force=True)
    plan.place("model-10", "Salon", x=200, y=210, rotation=180, force=True)
    found = issues(circulation.check(plan, "Salon"))
    sides = {c["side"] for c in found if c["label"] == "Table à manger"}
    assert sides == {"devant", "derrière"}
    assert all(c["min_cm"] == 110 for c in found if c["label"] == "Table à manger")


EXTRA = {
    "model-14": {
        **ITEMS["model-2"],
        "id": "model-14",
        "label": "Console",
        "w": 100,
        "d": 40,
        "h": 85,
        "menuCodes": ["M_TABLES"],
    },
    "model-15": {
        **ITEMS["model-2"],
        "id": "model-15",
        "label": "Lit superposé",
        "w": 190,
        "d": 90,
        "h": 160,
        "menuCodes": ["CH_LITS"],
    },
    "model-16": {
        **ITEMS["model-2"],
        "id": "model-16",
        "label": "Tabouret de bar",
        "w": 45,
        "d": 45,
        "h": 85,
        "menuCodes": [],
    },
}


def test_no_false_alarms_for_console_wall_bench_bunk_and_stools(monkeypatch):
    MODELS.update(EXTRA)
    try:
        plan = room_plan(monkeypatch)
        plan.place("model-14", "Salon", against_wall=0, offset=250)
        plan.place("model-10", "Salon", x=300, y=270, rotation=180, force=True)
        plan.place("model-15", "Salon", against_wall=3, offset=60)
        plan.place("model-13", "Salon", x=200, y=150, rotation=90, force=True)
        plan.place("model-16", "Salon", x=265, y=150, rotation=90, force=True)
        report = circulation.check(plan, "Salon")
        flagged = {c["label"] for c in issues(report)}
        assert not flagged & {"Console", "Chaise", "Lit superposé", "Tabouret de bar"}
        table = [c for c in issues(report) if c["label"] == "Table à manger"]
        assert all(c["free_cm"] > 40 for c in table)
    finally:
        for k in EXTRA:
            MODELS.pop(k)


def test_wardrobe_needs_75_in_front(monkeypatch):
    MODELS["model-17"] = {
        **ITEMS["model-2"],
        "id": "model-17",
        "label": "Armoire",
        "w": 100,
        "d": 60,
        "h": 200,
        "menuCodes": ["M_ARMOIRES"],
    }
    try:
        plan = room_plan(monkeypatch)
        plan.place("model-17", "Salon", x=330, y=150, rotation=90, force=True)
        plan.place("model-1", "Salon", x=205, y=150, rotation=90, force=True)
        found = [c for c in issues(circulation.check(plan, "Salon")) if c["label"] == "Armoire"]
        assert found and found[0]["min_cm"] == 75 and 60 <= found[0]["free_cm"] < 75
    finally:
        MODELS.pop("model-17")


def test_bar_height_table_is_an_island_needing_90(monkeypatch):
    MODELS["model-18"] = {
        **ITEMS["model-2"],
        "id": "model-18",
        "label": "Îlot",
        "w": 160,
        "d": 90,
        "h": 92,
        "menuCodes": ["M_TABLES"],
    }
    try:
        plan = room_plan(monkeypatch)
        plan.place("model-18", "Salon", x=200, y=150, rotation=0, force=True)
        found = [c for c in circulation.check(plan, "Salon")["clearances"] if c["label"] == "Îlot"]
        assert {c["min_cm"] for c in found} == {90}
        assert all(c["ok"] for c in found)
    finally:
        MODELS.pop("model-18")


def test_clearance_is_measured_to_the_centimetre(monkeypatch):
    plan = room_plan(monkeypatch)
    plan.place("model-11", "Salon", x=200, y=150, rotation=0, force=True)
    plan.place("model-12", "Salon", x=200, y=255, rotation=0, force=True)
    sofa = next(c for c in circulation.check(plan, "Salon")["clearances"] if c["label"] == "Canapé")
    assert sofa["free_cm"] == 30
