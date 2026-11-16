"""Project access is enforced on HTTP, files, workers, and live event streams."""
import json

import pytest
from fastapi.testclient import TestClient

from wholeboard import config, project, server


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    config.update({"projects_dir": str(tmp_path / "projects")})
    monkeypatch.setattr(server, "manager", project.Manager())
    owner = TestClient(server.app, client=("127.0.0.1", 5000))
    remote = TestClient(server.app, client=("192.0.2.11", 5000))
    p = owner.post("/api/workbench/projects", json={"title": "Private board", "example": True}).json()
    return owner, remote, p


def account(owner, name="designer"):
    result = owner.post("/api/workbench/accounts", json={"username": name, "display_name": "Design reviewer", "password": "local-only-test-password"})
    assert result.status_code == 201, result.text
    assert "password" not in result.json()
    return result.json()


def login(remote):
    response = remote.post("/api/workbench/session/login", json={"username": "designer", "password": "local-only-test-password"})
    assert response.status_code == 200, response.text
    assert response.cookies.get("wb_session")


def test_workspace_accounts_use_real_sessions_and_do_not_expose_other_projects(workspace):
    owner, remote, p = workspace
    member = account(owner)
    assert remote.get("/api/projects").status_code == 401
    login(remote)
    assert remote.get("/api/projects").json() == []
    assert remote.get(f"/api/projects/{p['id']}").status_code == 403
    membership = owner.put(f"/api/workbench/projects/{p['id']}/members/{member['id']}", json={"role": "editor"})
    assert membership.status_code == 200
    assert [r["id"] for r in remote.get("/api/projects").json()] == [p["id"]]
    spec = p["spec"]
    spec["components"][1]["value"] = "6.8k"
    saved = remote.put(f"/api/workbench/projects/{p['id']}/design", json={"base_version": 1, "spec": spec})
    assert saved.status_code == 200
    assert remote.get(f"/api/projects/{p['id']}").json()["state"]["access"]["role"] == "editor"
    assert remote.post("/api/config", json={"ai": {"provider": "openai"}}).status_code == 403
    assert remote.post("/api/workbench/accounts", json={"username": "attacker", "password": "password"}).status_code == 403
    assert remote.delete(f"/api/projects/{p['id']}").status_code == 403
    assert remote.post(f"/api/projects/{p['id']}/firmware/build").status_code == 403
    assert remote.put(f"/api/workbench/projects/{p['id']}/members/{member['id']}", json={"role": "owner"}).status_code == 403
    owner.put(f"/api/workbench/projects/{p['id']}/members/{member['id']}", json={"role": "viewer"})
    assert remote.put(f"/api/workbench/projects/{p['id']}/design", json={"base_version": 2, "spec": spec}).status_code == 403
    assert remote.post(f"/api/projects/{p['id']}/build", json={}).status_code == 403
    assert remote.post(f"/api/workbench/projects/{p['id']}/codex", json={"text": "Do not run"}).status_code == 403
    assert remote.post(f"/api/workbench/projects/{p['id']}/wire-cuts/prepare",json={'base_version':2,'wire':'unused','point':[0,0]}).status_code==403
    remote.post("/api/workbench/session/logout")
    assert remote.get(f"/api/projects/{p['id']}").status_code == 401


def test_project_ownership_follows_the_logged_in_creator(workspace):
    owner, remote, p = workspace
    account(owner)
    login(remote)
    created = remote.post("/api/workbench/projects", json={"title": "Member board", "example": True})
    assert created.status_code == 201
    pid = created.json()["id"]
    assert remote.get(f"/api/projects/{pid}").json()["state"]["access"]["role"] == "owner"
    assert remote.delete(f"/api/projects/{pid}").status_code == 200


def test_scoped_share_links_cannot_read_hidden_files_or_start_workers_and_can_be_revoked(workspace):
    owner, remote, p = workspace
    created = owner.post(f"/api/workbench/projects/{p['id']}/shares", json={"role": "viewer", "label": "Assembly review"})
    assert created.status_code == 201, created.text
    link = created.json()
    assert link["path"].startswith("/#share=")
    response = remote.post("/api/workbench/session/share", json={"token": link["path"].split("=", 1)[1]})
    assert response.status_code == 200
    assert response.json()["project_id"] == p["id"]
    assert response.cookies.get("wb_share")
    assert remote.get(f"/api/projects/{p['id']}").status_code == 200
    assert [r["id"] for r in remote.get("/api/projects").json()] == [p["id"]]
    assert remote.get(f"/api/projects/{p['id']}/files/design.json").status_code == 200
    server.mgr().get(p["id"]).root.joinpath(".private.txt").write_text("not shared")
    assert remote.get(f"/api/projects/{p['id']}/files/.private.txt").status_code == 403
    server.mgr().get(p["id"]).root.joinpath("public-alias.txt").symlink_to(".private.txt")
    assert remote.get(f"/api/projects/{p['id']}/files/public-alias.txt").status_code == 403
    assert remote.post(f"/api/projects/{p['id']}/cancel").status_code == 403
    assert remote.post(f"/api/workbench/projects/{p['id']}/engineering/enclosure", json={}).status_code == 403
    assert remote.post("/api/workbench/projects", json={"title": "No workspace access"}).status_code == 403
    assert remote.post("/mcp", json={}).status_code == 403
    assert remote.get("/api/config").status_code == 200
    assert owner.delete(f"/api/workbench/projects/{p['id']}/shares/{link['id']}").status_code == 200
    assert remote.get(f"/api/projects/{p['id']}").status_code == 401


def test_comments_preserve_identity_threads_anchors_and_live_permissions(workspace):
    owner, remote, p = workspace
    member = account(owner)
    login(remote)
    url = f"/api/workbench/projects/{p['id']}"
    owner.put(f"{url}/members/{member['id']}", json={"role": "commenter"})
    comment = remote.post(f"{url}/comments", json={"text": "Check this resistor", "author_name": "Workspace owner", "anchor": {"view": "schematic", "ref": "R1"}})
    assert comment.status_code == 201, comment.text
    comment = comment.json()
    assert comment["author_name"] == "Design reviewer"
    assert comment["anchor"] == {"view": "schematic", "ref": "R1"}
    reply = owner.post(f"{url}/comments", json={"text": "Reviewed", "parent_id": comment["id"]})
    assert reply.status_code == 201
    other = owner.post("/api/workbench/projects", json={"title": "Other", "example": True}).json()
    assert owner.post(f"/api/workbench/projects/{other['id']}/comments", json={"text": "Cross-project reply", "parent_id": comment["id"]}).status_code == 404
    assert remote.patch(f"{url}/comments/{reply.json()['id']}", json={"text": "Changed another author"}).status_code == 403
    assert remote.patch(f"{url}/comments/{comment['id']}", json={"resolved": True}).status_code == 200
    persisted = owner.get(f"{url}/comments").json()["comments"]
    assert persisted[0]["resolved"] is True
    assert persisted[1]["parent_id"] == comment["id"]
    owner.put(f"{url}/members/{member['id']}", json={"role": "viewer"})
    assert remote.post(f"{url}/comments", json={"text": "No comment access"}).status_code == 403
    assert remote.get(f"{url}/comments").status_code == 200


def test_revocation_closes_an_already_connected_project_stream(workspace):
    owner, remote, p = workspace
    member = account(owner)
    login(remote)
    url = f"/api/workbench/projects/{p['id']}"
    owner.put(f"{url}/members/{member['id']}", json={"role": "viewer"})
    after = len(server.mgr().get(p["id"]).events)
    with remote.websocket_connect(f"/api/projects/{p['id']}/ws?after={after}") as ws:
        owner.post(f"{url}/comments", json={"text": "Live review event"})
        event = json.loads(ws.receive_text())
        while event["type"] == "presence":
            event = json.loads(ws.receive_text())
        assert event["type"] == "comments_changed"
        owner.delete(f"{url}/members/{member['id']}")
        assert ws.receive()["code"] == 4403


def test_cookie_sessions_reject_cross_origin_mutations(workspace):
    owner, remote, p = workspace
    member = account(owner)
    login(remote)
    owner.put(f"/api/workbench/projects/{p['id']}/members/{member['id']}", json={"role": "editor"})
    response = remote.post(f"/api/projects/{p['id']}/cancel", headers={"origin": "https://unrelated.example"})
    assert response.status_code == 403


def test_cloning_a_shared_project_cannot_copy_hidden_files_through_public_aliases(workspace):
    owner, remote, p = workspace
    user = account(owner)
    login(remote)
    owner.put(f"/api/workbench/projects/{p['id']}/members/{user['id']}", json={"role": "viewer"})
    source = server.mgr().get(p["id"])
    (source.root / ".private.md").write_text("Private project note")
    (source.root / "public-alias.md").symlink_to(".private.md")
    (source.root / "state-alias.json").symlink_to("state.json")
    cloned = remote.post(f"/api/workbench/projects/{p['id']}/clone", json={"title": "Viewer copy"})
    assert cloned.status_code == 201
    target = server.mgr().get(cloned.json()["id"])
    assert not (target.root / "public-alias.md").exists()
    assert not (target.root / "state-alias.json").exists()


def test_accounts_and_links_store_only_hashed_credentials_and_expire(workspace):
    from wholeboard import collaboration
    owner, remote, p = workspace
    member = account(owner)
    login(remote)
    session_token = remote.cookies.get("wb_session")
    with collaboration.database() as db:
        assert db.execute("SELECT password FROM users WHERE id=?", (member["id"],)).fetchone()[0].startswith("pbkdf2_sha256$")
        assert db.execute("SELECT hash FROM sessions").fetchone()[0] != session_token
    owner.patch(f"/api/workbench/accounts/{member['id']}", json={"disabled": True})
    assert remote.get("/api/projects").status_code == 401
    response = owner.post(f"/api/workbench/projects/{p['id']}/shares", json={"role": "commenter"}).json()
    token = response["path"].split("=", 1)[1]
    with collaboration.database() as db:
        assert db.execute("SELECT hash FROM shares WHERE id=?", (response["id"],)).fetchone()[0] != token
        db.execute("UPDATE shares SET expires=0 WHERE id=?", (response["id"],))
    assert remote.post("/api/workbench/session/share", json={"token": token}).status_code == 404


def test_live_presence_uses_the_authenticated_identity_and_is_not_persisted(workspace):
    owner, remote, p = workspace
    member = account(owner)
    login(remote)
    url = f"/api/workbench/projects/{p['id']}"
    owner.put(f"{url}/members/{member['id']}", json={"role": "viewer"})
    after = len(server.mgr().get(p["id"]).events)
    with remote.websocket_connect(f"/api/projects/{p['id']}/ws?after={after}") as ws:
        owner.post(f"{url}/comments", json={"text": "Flush stream"})
        first = json.loads(ws.receive_text())
        assert first["type"] == "presence"
        assert first["users"][0]["name"] == "Design reviewer"
        ws.send_json({"type": "presence", "name": "Forged owner", "view": "schematic", "ref": "R1", "sheet": "", "cursor": [200, 300]})
        current = json.loads(ws.receive_text())
        while current["type"] != "presence" or not current["users"][0].get("cursor"):
            current = json.loads(ws.receive_text())
        assert current["users"][0]["name"] == "Design reviewer"
        assert current["users"][0]["ref"] == "R1"
        assert current["users"][0]["cursor"] == [200, 300]
    assert not any(e["type"] == "presence" for e in server.mgr().get(p["id"]).events)
