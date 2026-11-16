"""Production handoffs freeze actual files and never manufacture supplier evidence."""
import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wholeboard import collaboration, config, project, server


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    config.update({"projects_dir": str(tmp_path / "projects")})
    monkeypatch.setattr(server, "manager", project.Manager())
    http = TestClient(server.app)
    made = http.post("/api/workbench/projects", json={"title": "Production test", "example": True})
    assert made.status_code == 201, made.text
    p = server.mgr().get(made.json()["id"])
    folder = p.root / "manufacturing"
    folder.mkdir()
    with zipfile.ZipFile(folder / "board-gerbers.zip", "w") as archive:
        archive.writestr("board-F_Cu.gbr", "G04 software test fixture, not physical manufacturing evidence*\nM02*")
    (folder / "board-bom.csv").write_text("Designator,MPN,Footprint\nR1,TEST-0603,R_0603\n")
    (folder / "board-cpl.csv").write_text("Designator,Mid X,Mid Y,Layer,Rotation\nR1,10,10,Top,0\n")
    return http, p


def freeze(http, p, **changes):
    body = {"base_version": p.state["workbench"]["version"], "scope": "pcba", "quantity": 5,
            "files_match_design": True, "files": [
                {"role": "gerbers", "path": "manufacturing/board-gerbers.zip"},
                {"role": "bom", "path": "manufacturing/board-bom.csv"},
                {"role": "cpl", "path": "manufacturing/board-cpl.csv"}], **changes}
    return http.post(f"/api/projects/{p.id}/production/packages", json=body)


def inquiry(http, p):
    package = freeze(http, p)
    assert package.status_code == 201, package.text
    result = http.post(f"/api/projects/{p.id}/production/rfqs", json={
        "package_id": package.json()["id"], "supplier_id": "pcbway", "target_budget": 150,
        "currency": "USD", "contact_email": "supplier@example.test"})
    assert result.status_code == 201, result.text
    rfq = result.json()
    portal = rfq["supplier_url"].replace("/production/supplier/", "/api/production/supplier/")
    return rfq, portal


def offer(revision=1, **changes):
    return {"base_revision": revision, "decision": "quote", "supplier_name": "Test supplier",
            "contact_name": "Engineer", "reference": "Q-100", "currency": "USD",
            "line_items": [{"item": "Materials", "amount": 40}, {"item": "Assembly", "amount": 10}],
            "lead_time_days": 7, "valid_until": (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat(),
            **changes}


def test_frozen_package_contains_hashed_files_and_preserves_editor(setup):
    http, p = setup
    before = json.loads(json.dumps(p.state))
    response = freeze(http, p)
    assert response.status_code == 201, response.text
    frozen = response.json()
    assert frozen["missing_roles"] == []
    assert frozen["source_version"] == 1
    assert p.state == before
    source = p.root / "manufacturing/board-bom.csv"
    original = source.read_bytes()
    source.write_text("changed after freezing")
    download = http.get(frozen["download_url"])
    assert hashlib.sha256(download.content).hexdigest() == frozen["archive_sha256"]
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert archive.read("files/board-bom.csv") == original
        manifest = json.loads(archive.read("manifest.json"))
        row = next(f for f in manifest["files"] if f["role"] == "bom")
        assert row["sha256"] == hashlib.sha256(original).hexdigest()
        assert "state.json" not in archive.namelist()
    catalog = http.get(f"/api/workbench/projects/{p.id}/files").json()
    assert not any(".production" in row["path"] for row in catalog["files"])


@pytest.mark.parametrize("path", ["../config.json", ".env", "state.json", "history/1.json", "manufacturing/link.csv"])
def test_package_rejects_private_and_symlink_sources(setup, path):
    http, p = setup
    (p.root / ".env").write_text("SECRET=never-export")
    (p.root / "manufacturing/link.csv").symlink_to(p.root / "manufacturing/board-bom.csv")
    response = freeze(http, p, files=[{"role": "bom", "path": path}])
    assert response.status_code == 422, response.text
    assert "never-export" not in response.text


def test_package_versions_and_idempotency_prevent_mixed_or_duplicate_snapshots(setup):
    http, p = setup
    result = freeze(http, p, idempotency_key="freeze-1")
    assert result.status_code == 201, result.text
    same = freeze(http, p, idempotency_key="freeze-1")
    assert same.json()["id"] == result.json()["id"]
    conflict = freeze(http, p, idempotency_key="freeze-1", quantity=20)
    assert conflict.status_code == 409
    assert freeze(http, p, base_version=0).status_code == 409
    listed = http.get(f"/api/projects/{p.id}/production").json()
    assert len(listed["packages"]) == 1


def test_incomplete_package_can_be_reviewed_but_cannot_be_sent_as_complete(setup):
    http, p = setup
    response = freeze(http, p, files=[{"role": "bom", "path": "manufacturing/board-bom.csv"}])
    assert response.status_code == 201, response.text
    assert set(response.json()["missing_roles"]) == {"gerbers", "cpl"}
    refused = http.post(f"/api/projects/{p.id}/production/rfqs", json={
        "package_id": response.json()["id"], "supplier_id": "jlcpcb"})
    assert refused.status_code == 409


def test_rfq_quote_acceptance_and_supplier_progress_complete_a_real_manual_workflow(setup):
    http, p = setup
    rfq, portal = inquiry(http, p)
    assert rfq["status"] == "prepared"
    public = http.get(portal)
    assert public.status_code == 200, public.text
    assert public.json()["supplier"]["id"] == "pcbway"
    assert "spec" not in public.json() and "supplier_url" not in public.text
    assert http.get(portal + "/package").status_code == 200
    offered = http.post(portal + "/quote", json=offer())
    assert offered.status_code == 200, offered.text
    rfq = offered.json()
    assert rfq["status"] == "quoted"
    quote = rfq["quotes"][-1]
    assert quote["total"] == 50
    assert quote["source"] == "supplier_portal" and quote["identity_verified"] is False
    assert http.post(portal + "/events", json={"status": "production", "note": "Started"}).status_code == 409
    accepted = http.post(f"/api/projects/{p.id}/production/rfqs/{rfq['id']}/accept", json={"quote_id": quote["id"]})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    for status in ("engineering_review", "materials", "production", "testing", "shipped", "delivered"):
        progress = http.post(portal + "/events", json={"status": status, "note": status + " confirmed by link holder"})
        assert progress.status_code == 200, progress.text
    assert progress.json()["status"] == "delivered"
    reloaded = http.get(f"/api/projects/{p.id}/production").json()["rfqs"][0]
    assert reloaded["status"] == "delivered"
    assert reloaded["accepted_quote_id"] == quote["id"]
    assert len(reloaded["events"]) >= 9
    assert p.state["workbench"]["version"] == 1


def test_portal_token_rotates_expires_and_cannot_open_other_project_routes(setup, monkeypatch):
    http, p = setup
    rfq, old = inquiry(http, p)
    rotated = http.post(f"/api/projects/{p.id}/production/rfqs/{rfq['id']}/invite", json={})
    assert rotated.status_code == 200, rotated.text
    assert http.get(old).status_code == 404
    new = rotated.json()["supplier_url"].replace("/production/supplier/", "/api/production/supplier/")
    assert http.get(new).status_code == 200
    from wholeboard.production import service
    now = service.time.time()
    monkeypatch.setattr(service.time, "time", lambda: now + 8 * 86400)
    assert http.get(new).status_code == 404


def test_stale_supplier_reply_is_not_applied_and_expired_quote_cannot_be_accepted(setup):
    http, p = setup
    rfq, portal = inquiry(http, p)
    quoted = http.post(portal + "/quote", json=offer()).json()
    assert http.post(portal + "/quote", json=offer()).status_code == 409
    expired = http.post(portal + "/quote", json=offer(revision=quoted["revision"], valid_until="2000-01-01"))
    assert expired.status_code == 422
    assert http.get(portal).json()["rfq"]["revision"] == quoted["revision"]


def test_manual_submission_requires_an_explicit_external_handoff(setup):
    http, p = setup
    rfq, portal = inquiry(http, p)
    path = f"/api/projects/{p.id}/production/rfqs/{rfq['id']}"
    assert http.post(path + "/submit", json={"channel": "manual"}).status_code == 422
    sent = http.post(path + "/submit", json={"channel": "manual", "sent": True, "external_reference": "Mail reference ABC"})
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "submitted"
    assert sent.json()["events"][-1]["source"] == "buyer_recorded_handoff"
    sync = http.post(path + "/sync", json={})
    assert sync.status_code == 409
    assert http.get(portal).json()["rfq"]["status"] == "submitted"


def test_supplier_portal_is_accessible_remotely_without_granting_workspace_access(setup):
    http, p = setup
    rfq, portal = inquiry(http, p)
    with collaboration.database() as db:
        db.execute("INSERT INTO workspace(key,value) VALUES('configured','1')")
    remote = TestClient(server.app, client=("198.51.100.15", 50000))
    assert remote.get(portal).status_code == 200
    assert remote.post(portal + "/quote", json=offer()).status_code == 200
    assert remote.get(f"/api/projects/{p.id}").status_code == 401
    assert remote.get("/api/production/supplier/invalid-token").status_code == 404
    assert remote.post(portal + "/events", json={"status": "materials", "note": "Started"}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_viewer_cannot_create_packages_or_see_supplier_secrets(setup, monkeypatch):
    http, p = setup
    inquiry(http, p)
    monkeypatch.setattr(collaboration, "identity", lambda scope: {"id": "reviewer", "mode": "share", "admin": False,
        "project_id": p.id, "role": "viewer", "name": "Reviewer"})
    assert freeze(http, p).status_code == 403
    data = http.get(f"/api/projects/{p.id}/production")
    assert data.status_code == 200, data.text
    assert "token_hash" not in data.text and "supplier_url" not in data.text


@pytest.mark.parametrize("amount", [-1, "NaN", "Infinity", True])
def test_supplier_quote_rejects_invalid_money_without_saving(setup, amount):
    http, p = setup
    _, portal = inquiry(http, p)
    response = http.post(portal + "/quote", json=offer(line_items=[{"item": "Price", "amount": amount}]))
    assert response.status_code == 422, response.text
    assert http.get(portal).json()["rfq"]["quotes"] == []


def test_tampered_archive_is_not_delivered_to_either_party(setup):
    http, p = setup
    rfq, portal = inquiry(http, p)
    from wholeboard.production import service
    package = service.load(p)["packages"][rfq["package_id"]]
    (p.root / package["archive_path"]).write_bytes(b"tampered")
    assert http.get(package["download_url"]).status_code == 409
    assert http.get(portal + "/package").status_code == 409


def test_invalid_record_ids_and_scopes_return_validation_errors(setup):
    http, p = setup
    assert freeze(http, p, scope=[]).status_code == 422
    response = http.post(f"/api/projects/{p.id}/production/rfqs", json={"package_id": [], "supplier_id": "pcbway"})
    assert response.status_code == 422


def test_revoked_supplier_page_still_displays_a_safe_error_capable_ui(setup):
    http, _ = setup
    result = http.get("/production/supplier/invalid-token")
    assert result.status_code == 200
    assert "text/html" in result.headers["content-type"]


def test_estimates_persist_source_version_and_never_rewrite_the_design(setup):
    http, p = setup
    before = json.loads(json.dumps(p.state))
    result = http.post(f"/api/projects/{p.id}/production/estimates", json={
        "base_version": 1, "quantity": 5, "assembly": True, "shipping_country": "US", "use_ai": False})
    assert result.status_code == 201, result.text
    assert result.json()["source_version"] == 1
    assert result.json()["known_total"] > 0
    assert result.json()["ai"]["status"] != "complete"
    assert p.state == before
    assert http.get(f"/api/projects/{p.id}/production").json()["estimates"][0]["id"] == result.json()["id"]


def test_estimate_that_races_an_editor_save_is_not_published_as_current(setup, monkeypatch):
    http, p = setup
    from wholeboard.production import estimate
    original = estimate.build_estimate
    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        p.state["workbench"]["version"] += 1
        return result
    monkeypatch.setattr(estimate, "build_estimate", delayed)
    result = http.post(f"/api/projects/{p.id}/production/estimates", json={
        "base_version": 1, "quantity": 5, "assembly": False, "use_ai": False})
    assert result.status_code == 409
    assert http.get(f"/api/projects/{p.id}/production").json()["estimates"] == []


@pytest.mark.parametrize("changes", [{"currency": ["USD"]}, {"decision": ["quote"]}])
def test_malformed_public_quote_fields_return_validation_errors(setup, changes):
    http, p = setup
    _, portal = inquiry(http, p)
    result = http.post(portal + "/quote", json=offer(**changes))
    assert result.status_code == 422


def test_malformed_file_role_does_not_start_an_export_or_crash(setup):
    http, p = setup
    result = freeze(http, p, files=[{"role": ["bom"], "path": "manufacturing/board-bom.csv"}])
    assert result.status_code == 422


def test_supplier_brand_assets_remain_available_with_a_lan_password(setup):
    http, p = setup
    inquiry(http, p)
    config.update({"server": {"password_hash": "password-enabled-for-test"}})
    remote = TestClient(server.app, client=("198.51.100.15", 50000))
    response = remote.get("/static/openfabro-mascot.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_duplicate_archive_basenames_do_not_overwrite_another_frozen_file(setup):
    http, p = setup
    parent = p.root / "manufacturing"
    (parent / "sub").mkdir()
    paths = ["manufacturing/a.csv", "manufacturing/2-a.csv", "manufacturing/sub/a.csv"]
    for index, relative in enumerate(paths):
        (p.root / relative).write_text(f"Unique document {index}")
    result = freeze(http, p, files=[{"path": relative, "role": "bom"} for relative in paths])
    assert result.status_code == 201, result.text
    content = http.get(result.json()["download_url"]).content
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert len({row["archive_path"] for row in manifest["files"]}) == 3
        assert all(hashlib.sha256(archive.read(row["archive_path"])).hexdigest() == row["sha256"] for row in manifest["files"])


def test_native_bytes_edited_outside_the_saved_design_are_not_exported_as_current(setup):
    http, p = setup
    from wholeboard.production import service
    pcb = p.root / "manufacturing/board.kicad_pcb"
    pcb.write_bytes(b"original native snapshot")
    p.state["workbench_native"] = {"pcb": str(pcb), "fingerprint": service.digest(p.state["spec"]),
        "geometry_pcb_sha256": hashlib.sha256(pcb.read_bytes()).hexdigest()}
    pcb.write_bytes(b"external KiCad edit that is absent from the saved design")
    assert http.get(f"/api/projects/{p.id}/production").json()["can_export_native"] is False
    assert freeze(http, p, files=[]).status_code == 409


def test_estimate_retry_replays_saved_result_without_requesting_another_model_call(setup, monkeypatch):
    http, p = setup
    from wholeboard.production import estimate
    path = f"/api/projects/{p.id}/production/estimates"
    body = {"base_version": 1, "quantity": 5, "assembly": False, "use_ai": False, "idempotency_key": "same-inference"}
    result = http.post(path, json=body)
    assert result.status_code == 201, result.text
    def unavailable(*args, **kwargs):
        raise RuntimeError("A duplicate inference would spend resources while replay should work offline")
    monkeypatch.setattr(estimate, "build_estimate", unavailable)
    retried = http.post(path, json=body)
    assert retried.status_code == 201
    assert retried.json()["id"] == result.json()["id"]


def test_nonfinite_json_numbers_return_validation_errors_before_mutation(setup):
    http, p = setup
    result = http.post(f"/api/projects/{p.id}/production/packages", content='{"unrelated":1e999}',
                       headers={"Content-Type": "application/json"})
    assert result.status_code == 422


def test_native_export_keeps_only_assembly_parts_in_bom_and_placement_files(setup, monkeypatch):
    http, p = setup
    from wholeboard.production import service
    from wholeboard.kicad import cli
    p.state["spec"] = {"name": "assembly_filter", "board": {"width_mm": 20, "height_mm": 20, "layers": 2},
        "components": [{"ref": "R1", "value": "1k", "footprint": "Resistor_SMD:R_0603_1608Metric"},
            {"ref": "H1", "value": "Hole", "footprint": "MountingHole:MountingHole_2.2mm_M2"},
            {"ref": "TP1", "value": "Test pad", "footprint": "TestPoint:TestPoint_Pad_D1.0mm", "terminal": {"exclude_from_pcb": False}}], "nets": []}
    pcb = p.root / "manufacturing/board.kicad_pcb"
    pcb.write_bytes(b"native byte fixture for external exporter boundary")
    p.state["workbench_native"] = {"pcb": str(pcb), "fingerprint": service.digest(p.state["spec"]),
        "geometry_pcb_sha256": hashlib.sha256(pcb.read_bytes()).hexdigest()}
    def exported(source, folder, layers):
        # Native tool boundary: the application must use a verified copy of these
        # bytes, rather than exporting a mutable editor file in place.
        assert Path(source) != pcb
        assert Path(source).read_bytes() == pcb.read_bytes()
        folder.mkdir(parents=True, exist_ok=True)
        gerbers = folder / "board-gerbers.zip"
        with zipfile.ZipFile(gerbers, "w") as archive:
            archive.writestr("board.gbr", "fixture")
        positions = folder / "board-pos.csv"
        positions.write_text('Ref,Val,Package,PosX,PosY,Rot,Side\nR1,1k,R_0603_1608Metric,10,10,0,top\nH1,Hole,MountingHole,3,3,0,top\nTP1,Pad,TestPoint,5,5,0,top\n')
        return {"gerber_zip": str(gerbers), "pos": str(positions)}
    monkeypatch.setattr(cli, "export_fab", exported)
    frozen = freeze(http, p, files=[])
    assert frozen.status_code == 201, frozen.text
    with zipfile.ZipFile(io.BytesIO(http.get(frozen.json()["download_url"]).content)) as archive:
        for row in frozen.json()["files"]:
            if row["role"] in {"bom", "cpl"}:
                content = archive.read(row["archive_path"]).decode()
                assert "R1" in content and "H1" not in content and "TP1" not in content


def test_rfq_cannot_attach_a_bare_board_estimate_to_an_assembled_package(setup):
    http, p = setup
    estimate = http.post(f"/api/projects/{p.id}/production/estimates", json={
        "base_version": 1, "quantity": 5, "scope": "pcb", "assembly": False, "use_ai": False})
    assert estimate.status_code == 201, estimate.text
    package = freeze(http, p).json()
    response = http.post(f"/api/projects/{p.id}/production/rfqs", json={
        "package_id": package["id"], "supplier_id": "jlcpcb", "estimate_id": estimate.json()["id"]})
    assert response.status_code == 409
