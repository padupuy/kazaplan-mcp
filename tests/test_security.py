import asyncio
import sys
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from kazaplan_mcp import api, server
from tests.test_plan import make_plan


@pytest.fixture
def opened(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "BACKUPS", tmp_path / "backups")
    server.STATE.update(plan=make_plan(), plan_id="12345678", source="test", title="Test")
    yield tmp_path
    server.STATE.update(plan=None, plan_id=None, source=None, title=None)


def call(name, args):
    async def run():
        async with Client(server.mcp) as c:
            return await c.call_tool(name, args)

    return asyncio.run(run())


@pytest.mark.parametrize("bad", ["../../etc/x", "123/../456", "abc", "", "12 34"])
def test_plan_id_must_be_numeric(bad, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "BACKUPS", tmp_path)
    with pytest.raises(api.ApiError):
        api.backup(bad or "x", b"data", "orig")
    with pytest.raises(api.ApiError):
        api.upload(bad, "t", b"data")


def test_backup_stays_in_backup_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "BACKUPS", tmp_path)
    assert api.backup("12345678", b"x", "orig").parent == tmp_path
    assert api.backup(None, b"x", "orig").name.startswith("local-")


@pytest.mark.parametrize("target", ["evil.sh", ".zshrc", "plan.kzp.txt"])
def test_save_out_path_requires_kzp(opened, target):
    with pytest.raises(ToolError, match=".kzp"):
        call("kz_save", {"out_path": str(opened / target)})
    assert not (opened / target).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_save_out_path_refuses_symlink(opened):
    victim = opened / "victim.txt"
    victim.write_text("keep")
    (opened / "link.kzp").symlink_to(victim)
    with pytest.raises(ToolError):
        call("kz_save", {"out_path": str(opened / "link.kzp")})
    assert victim.read_text() == "keep"


def test_save_out_path_writes_kzp(opened):
    call("kz_save", {"out_path": str(opened / "ok.kzp")})
    assert (opened / "ok.kzp").read_bytes()[:4] == b"WPRJ"


def test_copy_plan_requires_whitelisted_target(opened, monkeypatch):
    monkeypatch.setenv("KZ_ALLOWED_PLANS", "12345678")
    with pytest.raises(ToolError, match="liste blanche"):
        call("kz_copy_plan", {"source_plan_id": "12345678", "target_plan_id": "999"})
    with pytest.raises(ToolError, match="identiques"):
        call("kz_copy_plan", {"source_plan_id": "12345678", "target_plan_id": "12345678"})


def test_copy_plan_backs_up_target_then_uploads_source(opened, monkeypatch):
    monkeypatch.setenv("KZ_ALLOWED_PLANS", "999")
    src = make_plan().to_bytes()
    files = {"111": (src, {"title": "Maison"}), "999": (b"old", {"title": "Vide"})}
    monkeypatch.setattr(api, "download", lambda pid: files[pid])
    sent = {}
    monkeypatch.setattr(
        api, "upload", lambda pid, title, data: sent.update(pid=pid, title=title, data=data) or {}
    )
    call("kz_copy_plan", {"source_plan_id": "111", "target_plan_id": "999"})
    assert sent == {"pid": "999", "title": "Maison (copie)", "data": src}
    backups = sorted(p.name for p in (opened / "backups").iterdir())
    assert any("before-copy" in n for n in backups)
    assert server.STATE["plan_id"] == "999"


def test_sketch_writes_only_in_data_dir(opened, monkeypatch):
    from .test_plan import ITEMS

    monkeypatch.setattr("kazaplan_mcp.catalog.get", ITEMS.get)
    monkeypatch.setattr(server, "SKETCHES", opened / "sketches")
    with pytest.raises(ToolError):
        call("kz_sketch", {"out_path": str(opened / "evil.svg")})
    assert not (opened / "evil.svg").exists()
    out = call("kz_sketch", {"room": "../../Salon"}).data
    assert Path(out["svg_path"]).parent == (opened / "sketches").resolve()


def test_data_dir_follows_env(monkeypatch, tmp_path):
    from kazaplan_mcp import paths

    monkeypatch.setenv("KZ_DATA_DIR", str(tmp_path))
    assert paths.data_dir() == tmp_path
    monkeypatch.delenv("KZ_DATA_DIR")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    if sys.platform != "win32":
        assert paths.data_dir() == tmp_path / "xdg" / "kazaplan-mcp"


def test_catalog_missing_gives_actionable_message(monkeypatch, tmp_path):
    from kazaplan_mcp import catalog

    monkeypatch.setattr(catalog, "CACHE", tmp_path)
    catalog.index.cache_clear()
    with pytest.raises(FileNotFoundError, match="kazaplan-mcp catalog"):
        catalog.index()
    catalog.index.cache_clear()
