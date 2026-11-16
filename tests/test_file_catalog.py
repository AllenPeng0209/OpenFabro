"""A folder browser must enumerate complete, scoped files and label actual active outputs."""
import hashlib
import json

import pytest

from test_workbench import client, draft
from wholeboard import server
from wholeboard import codex_bridge


def fixture(client):
    made = draft(client)
    return made["id"], server.mgr().get(made["id"])


def test_file_catalog_pages_every_visible_file_beyond_the_old_thousand_limit(client):
    pid, project = fixture(client)
    folder = project.root / "docs" / "reports"
    folder.mkdir(parents=True)
    for index in range(1205):
        (folder / f"r{index:04}.md").write_text(f"Report {index}")
    first = client.get(f"/api/workbench/projects/{pid}/files", params={"limit": 127}).json()
    assert first.get("total", 0) >= 1207, "The catalog silently stops at one thousand entries"
    assert first["truncated"] and first["next_offset"] == 127
    entries = first["files"]
    cursor = first["next_offset"]
    while cursor < first["total"]:
        response = client.get(f"/api/workbench/projects/{pid}/files", params={"offset": cursor, "limit": 127, "expected_index_sha256": first["index_sha256"]})
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["index_sha256"] == first["index_sha256"]
        assert page["next_offset"] > cursor
        entries += page["files"]
        cursor = page["next_offset"]
    paths = [entry["path"] for entry in entries]
    assert len(paths) == len(set(paths)) == first["total"]
    assert len([path for path in paths if path.startswith("docs/reports/")]) == 1205
    assert "history/design-v1.json" in paths
    assert "state.json" not in paths and "events.jsonl" not in paths
    assert project.state["workbench"]["version"] == 1


def test_catalog_rejects_a_changed_file_or_current_generation_between_pages(client):
    pid, project = fixture(client)
    (project.root / "notes.md").write_text("First")
    first = client.get(f"/api/workbench/projects/{pid}/files", params={"limit": 1}).json()
    (project.root / "notes.md").write_text("Changed content, same path")
    response = client.get(f"/api/workbench/projects/{pid}/files", params={"offset": 1, "expected_index_sha256": first.get("index_sha256", "0" * 64)})
    assert response.status_code == 409, "Pages of different inventories must not be combined"
    current = client.get(f"/api/workbench/projects/{pid}/files").json()
    project.state["workbench"]["version"] = 2
    project.save()
    assert client.get(f"/api/workbench/projects/{pid}/files", params={"expected_index_sha256": current["index_sha256"]}).status_code == 409


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 2001}, {"offset": -1}, {"offset": "bad"}, {"expected_index_sha256": "bad"}])
def test_catalog_rejects_invalid_paging_and_index_hashes(client, params):
    pid, _ = fixture(client)
    assert client.get(f"/api/workbench/projects/{pid}/files", params=params).status_code == 422


def test_native_roles_use_full_metadata_paths_and_fingerprint_not_basename(client):
    pid, project = fixture(client)
    folder = project.root / "native" / "current-generation"
    other = project.root / "native" / "other-generation"
    folder.mkdir(parents=True)
    other.mkdir()
    for name in ("board.kicad_pcb", "board.kicad_sch", "geometry.json", "geometry-v4-abcdef123456.json"):
        (folder / name).write_text("Native fixture")
    (other / "geometry.json").write_text("Earlier geometry")
    (other / "board.kicad_pcb").write_text("Another native fixture")
    (other / "board.kicad_sch").write_text("Another schematic fixture")
    fingerprint = hashlib.sha256(json.dumps(project.state["spec"], sort_keys=True).encode()).hexdigest()
    project.state["workbench_native"] = {"schema": 17, "geometry_schema": 4, "fingerprint": fingerprint, "pcb": str(folder / "board.kicad_pcb"), "sch": str(folder / "board.kicad_sch"), "geometry_file": str(folder / "geometry-v4-abcdef123456.json")}
    project.save()
    first = client.get(f"/api/workbench/projects/{pid}/files").json()
    assert first.get("native", {}).get("status") == "current"
    assert first["native"]["folder"] == "native/current-generation"
    entries = {item["path"]: item for item in first["files"]}
    active = entries["native/current-generation/geometry-v4-abcdef123456.json"]
    assert active["native_role"] == "geometry" and active["native_status"] == "current"
    assert entries["native/current-generation/geometry.json"]["native_role"] == "older_geometry"
    assert entries["native/other-generation/geometry.json"]["native_status"] == "saved"
    assert not any(item["text_editable"] for path, item in entries.items() if path.startswith(("native/", "history/")))
    assert entries["design.json"]["text_editable"] is True
    previous_native = dict(project.state["workbench_native"])
    project.state["workbench_native"] = {**previous_native, "pcb": str(other / "board.kicad_pcb"), "sch": str(other / "board.kicad_sch"), "geometry_file": str(other / "geometry.json")}
    project.save()
    assert client.get(f"/api/workbench/projects/{pid}/files", params={"expected_index_sha256": first["index_sha256"]}).status_code == 409, "Changing only the active pointer must invalidate old pages"
    assert client.get(f"/api/workbench/projects/{pid}/files").json()["native"]["folder"] == "native/other-generation"
    project.state["workbench_native"] = previous_native
    project.save()
    changed = json.loads(json.dumps(project.state["spec"]))
    changed["summary"] = "New unsynthesized design"
    response = client.put(f"/api/workbench/projects/{pid}/design", json={"base_version": 1, "spec": changed})
    assert response.status_code == 200
    latest = client.get(f"/api/workbench/projects/{pid}/files").json()
    assert latest["native"]["status"] == "stale" and latest["design_version"] == 2
    assert latest["index_sha256"] != first["index_sha256"]


def test_catalog_excludes_hidden_and_symlink_paths_and_encodes_real_file_urls(client, tmp_path):
    pid, project = fixture(client)
    docs = project.root / "docs"
    docs.mkdir()
    name = '外壳 #1?".md'
    target = docs / name
    target.write_text("# Assembly")
    (docs / ".private.md").write_text("Private")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("Outside project")
    (docs / "outside").symlink_to(outside, target_is_directory=True)
    (docs / "alias.md").symlink_to(target)
    (project.root / ".hidden").mkdir()
    (project.root / ".hidden" / "ignored.md").write_text("Hidden")
    response = client.get(f"/api/workbench/projects/{pid}/files").json()
    files = {item["path"]: item for item in response["files"]}
    assert "docs/alias.md" not in files and "docs/outside/secret.md" not in files
    assert not any(".private" in path or ".hidden" in path for path in files)
    entry = files["docs/" + name]
    assert "%23" in entry["url"] and "%3F" in entry["url"] and "%22" in entry["url"]
    downloaded = client.get(entry["url"])
    assert downloaded.status_code == 200 and downloaded.text == "# Assembly"


def test_invalid_native_references_do_not_disclose_external_paths_or_claim_current(client, tmp_path):
    pid, project = fixture(client)
    outside = tmp_path / "outside.kicad_pcb"
    outside.write_text("Outside")
    project.state["workbench_native"] = {"fingerprint": hashlib.sha256(json.dumps(project.state["spec"], sort_keys=True).encode()).hexdigest(), "pcb": str(outside)}
    project.save()
    result = client.get(f"/api/workbench/projects/{pid}/files").json()
    assert result.get("native", {}).get("status") == "unavailable"
    assert str(outside) not in json.dumps(result)


def test_case_aliases_cannot_write_native_history_or_root_design_files(client):
    pid, project = fixture(client)
    folder = project.root / "native" / "snapshot"
    folder.mkdir(parents=True)
    target = folder / "notes.md"
    target.write_text("Original native snapshot")
    alias = project.root / "NATIVE" / "snapshot" / "notes.md"
    if not alias.exists():
        pytest.skip("The test filesystem is case sensitive")
    original = target.read_bytes()
    response = client.put(f"/api/workbench/projects/{pid}/text/NATIVE/snapshot/notes.md", json={"content": "Overwrite", "base_sha": hashlib.sha256(original).hexdigest()})
    assert response.status_code == 422 and target.read_bytes() == original, "Case aliases bypass native snapshot protection"
    for path in ("HISTORY/design-v1.json", "DESIGN.JSON", "STATE.JSON"):
        response = client.put(f"/api/workbench/projects/{pid}/text/{path}", json={"content": "Overwrite", "base_sha": None})
        assert response.status_code == 422, path


def test_agent_file_proposals_cannot_use_a_case_alias_to_overwrite_native_files(client):
    pid, project = fixture(client)
    folder = project.root / "native" / "snapshot"
    folder.mkdir(parents=True)
    target = folder / "notes.md"
    target.write_text("Original native snapshot")
    if not (project.root / "NATIVE" / "snapshot" / "notes.md").exists():
        pytest.skip("The test filesystem is case sensitive")
    proposal = {"message": "Review", "files": [{"path": "NATIVE/snapshot/notes.md", "content": "Overwrite"}], "review": [], "tools": [], "design_json": None}
    with pytest.raises(ValueError, match="path"):
        codex_bridge.apply_result(project, proposal, "agent", 1)
    assert target.read_text() == "Original native snapshot" and project.state["workbench"]["version"] == 1
