"""Local workspace identities, project roles, revocable links, and review threads.

The desktop remains its workspace administrator. Enabling accounts or link sharing
also makes remote access private; the old optional LAN password still works for
the workspace administrator. Sessions and link secrets are stored only as hashes.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
from http.cookies import SimpleCookie
import json
import math
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit
import uuid

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from . import auth, config

ROLES = {"viewer": 10, "commenter": 20, "editor": 30, "owner": 40}
COOKIE = "wb_session"
SHARE_COOKIE = "wb_share"
LIFETIME = 30 * 86400


def database_path():
    return config.APP_DIR / "workspace.sqlite3"


@contextmanager
def database():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS workspace (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, password TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS members (project_id TEXT NOT NULL, user_id TEXT NOT NULL, role TEXT NOT NULL,
            PRIMARY KEY (project_id,user_id));
        CREATE TABLE IF NOT EXISTS shares (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, hash TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL, label TEXT NOT NULL, expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS comments (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, author_id TEXT NOT NULL,
            author_name TEXT NOT NULL, text TEXT NOT NULL, anchor TEXT NOT NULL, parent_id TEXT,
            resolved INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS comments_project ON comments(project_id,created);
        """)
        path.chmod(0o600)
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def enabled() -> bool:
    if not database_path().exists():
        return False
    with database() as db:
        return db.execute("SELECT 1 FROM workspace WHERE key='configured'").fetchone() is not None


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def identity(scope: dict, *, refresh=False) -> dict:
    if not refresh and "wb_identity" in scope:
        return scope["wb_identity"]
    headers = dict(scope.get("headers") or [])
    cookie = SimpleCookie()
    try:
        cookie.load(headers.get(b"cookie", b"").decode("latin1"))
    except Exception:
        pass
    bearer = headers.get(b"authorization", b"").decode("latin1")
    token = bearer[7:] if bearer.startswith("Bearer ") else next((cookie[c].value for c in (SHARE_COOKIE, COOKIE) if c in cookie), "")
    guest = {"id": "", "name": "Guest", "admin": False, "mode": "anonymous"}
    if token:
        if not database_path().exists():
            return guest
        with database() as db:
            if token.startswith("wbs_"):
                row = db.execute("SELECT * FROM shares WHERE hash=? AND expires>? AND revoked=0", (token_hash(token), time.time())).fetchone()
                return {"id": "share:" + row["id"], "name": row["label"] or "Guest reviewer", "admin": False, "mode": "share",
                        "project_id": row["project_id"], "role": row["role"]} if row else guest
            row = db.execute("SELECT u.id,u.name FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.hash=? AND s.expires>? AND u.disabled=0", (token_hash(token), time.time())).fetchone()
            return {"id": row["id"], "name": row["name"], "admin": False, "mode": "account"} if row else guest
    if not enabled() or auth.is_local(scope) or auth.valid_token(auth._cookie(scope)):
        return {"id": "device", "name": config.load().get("workspace", {}).get("display_name") or "Workspace owner", "admin": True, "mode": "device"}
    return guest


def project_role(actor: dict, p) -> str | None:
    if actor.get("admin"):
        return "owner"
    if not actor.get("id"):
        return None
    if actor["mode"] == "share":
        return actor["role"] if actor["project_id"] == p.id else None
    if p.state.get("owner_id", "device") == actor["id"]:
        return "owner"
    with database() as db:
        row = db.execute("SELECT role FROM members WHERE project_id=? AND user_id=?", (p.id, actor["id"])).fetchone()
        return row["role"] if row else None


def access(actor: dict, p) -> dict:
    role = project_role(actor, p)
    rank = ROLES.get(role, 0)
    return {"role": role, "can_edit": rank >= 30, "can_comment": rank >= 20, "can_manage": rank >= 40,
            "admin": bool(actor.get("admin")), "shared": actor["mode"] == "share", "user": {"id": actor["id"], "name": actor["name"]}}


class AccessMiddleware:
    def __init__(self, app, get_manager):
        self.app, self.get_manager = app, get_manager

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        actor = identity(scope)
        scope["wb_identity"] = actor
        path, method = scope.get("path", "/"), scope.get("method", "GET")
        public = path in {"/", "/login", "/api/login", "/api/logout", "/favicon.ico", "/api/workbench/session", "/api/workbench/session/login", "/api/workbench/session/logout", "/api/workbench/session/share"} or path.startswith(("/static/", "/assets/"))
        status, detail = 0, ""
        headers = dict(scope.get("headers") or [])
        origin = headers.get(b"origin", b"").decode("latin1")
        if origin and (method not in ("GET", "HEAD", "OPTIONS") or scope["type"] == "websocket") and urlsplit(origin).netloc != headers.get(b"host", b"").decode("latin1"):
            status, detail = 403, "Use this workspace's own page to make changes."
        elif public or actor.get("admin"):
            return await self.app(scope, receive, send)
        elif not actor.get("id"):
            status, detail = 401, "Sign in to this workspace or open a shared project link."
        else:
            match = re.fullmatch(r"/api/(?:workbench/)?projects/([^/]+)(/.*)?", path)
            if match:
                p = self.get_manager().get(match[1])
                suffix = match[2] or ""
                rank = ROLES.get(project_role(actor, p), 0) if p else 0
                needed = 10 if method in ("GET", "HEAD") else 30
                if suffix.startswith(("/members", "/shares")) or (not suffix and method == "DELETE") or suffix == "/publish":
                    needed = 40
                if suffix.startswith("/comments"):
                    needed = 10 if method in ("GET", "HEAD") else 20
                if suffix in ("/native", "/checks", "/layer-preview"):
                    needed = 10
                if suffix == "/clone":
                    needed = 10 if actor["mode"] == "account" else 100
                private_file = any(s.startswith(".") for s in suffix.split("/") if s)
                if private_file or suffix in ("/tool", "/open-folder", "/firmware/build") or rank < needed:
                    status, detail = 403, "Your project role does not allow this action."
            elif method in ("GET", "HEAD") and path in {"/api/projects", "/api/config", "/api/status", "/api/workbench/example", "/api/workbench/codex/status", "/api/workbench/accounts"}:
                if path == "/api/workbench/accounts" and actor["mode"] == "share":
                    status, detail = 403, "This link only grants access to its project."
            elif method in ("GET", "HEAD") and path.startswith(("/api/workbench/library", "/api/workbench/parts/")):
                pass
            elif method == "POST" and path == "/api/workbench/schematic-view":
                pass
            elif method == "POST" and path in ("/api/workbench/projects", "/api/projects", "/api/import") and actor["mode"] == "account":
                pass
            else:
                status, detail = 403, "Only the workspace administrator can use this action."
        if status:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4401 if status == 401 else 4403})
            else:
                await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _role(value) -> str:
    if value not in ("viewer", "commenter", "editor"):
        raise HTTPException(422, "Choose Viewer, Commenter, or Editor.")
    return value


def _comment(row) -> dict:
    return {**dict(row), "anchor": json.loads(row["anchor"]), "resolved": bool(row["resolved"])}


def attach_collaboration(app, get_manager):
    def project(pid):
        p = get_manager().get(pid)
        if not p:
            raise HTTPException(404, "Project not found.")
        return p

    @app.get("/api/workbench/session")
    def session(request: Request):
        actor = identity(request.scope)
        return {"enabled": enabled(), "authenticated": bool(actor["id"]), "admin": actor["admin"], "mode": actor["mode"], "user": {"id": actor["id"], "name": actor["name"]}}

    @app.post("/api/workbench/session/login")
    async def login(request: Request):
        if not auth.allow_attempt(request.client.host if request.client else "?"):
            raise HTTPException(429, "Too many attempts. Try again in a minute.")
        body = await request.json()
        with database() as db:
            row = db.execute("SELECT * FROM users WHERE username=? AND disabled=0", (str(body.get("username", "")).strip().lower(),)).fetchone()
            valid = await asyncio.to_thread(auth.check_password, str(body.get("password", "")), row["password"] if row else auth.hash_password(secrets.token_urlsafe(24)))
            if not valid or not row:
                raise HTTPException(401, "The username or password is incorrect.")
            token = "wbu_" + secrets.token_urlsafe(32)
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (token_hash(token), row["id"], time.time() + LIFETIME))
        response = JSONResponse({"user": {"id": row["id"], "name": row["name"]}})
        response.set_cookie(COOKIE, token, max_age=LIFETIME, httponly=True, samesite="lax", secure=request.url.scheme == "https")
        response.delete_cookie(SHARE_COOKIE)
        return response

    @app.post("/api/workbench/session/logout")
    def logout(request: Request):
        token = request.cookies.get(COOKIE)
        if token and database_path().exists():
            with database() as db:
                db.execute("DELETE FROM sessions WHERE hash=?", (token_hash(token),))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE)
        response.delete_cookie(SHARE_COOKIE)
        return response

    @app.post("/api/workbench/session/share")
    async def accept_share(request: Request):
        token = str((await request.json()).get("token") or "")
        with database() as db:
            row = db.execute("SELECT * FROM shares WHERE hash=? AND expires>? AND revoked=0", (token_hash(token), time.time())).fetchone()
        if not row or not get_manager().get(row["project_id"]):
            raise HTTPException(404, "This project link has expired or been revoked.")
        response = JSONResponse({"project_id": row["project_id"], "role": row["role"]})
        response.set_cookie(SHARE_COOKIE, token, max_age=max(1, int(row["expires"] - time.time())), httponly=True, samesite="lax", secure=request.url.scheme == "https")
        return response

    @app.get("/api/workbench/accounts")
    def accounts():
        with database() as db:
            return {"accounts": [dict(r) for r in db.execute("SELECT id,username,name,disabled FROM users ORDER BY username")]}

    @app.post("/api/workbench/accounts", status_code=201)
    async def create_account(request: Request):
        body = await request.json()
        username = str(body.get("username") or "").strip().lower()
        password = str(body.get("password") or "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,39}", username) or not 10 <= len(password) <= 256:
            raise HTTPException(422, "Use a 2–40 character username and a password of at least 10 characters.")
        name = str(body.get("display_name") or username).strip()[:80]
        user_id = uuid.uuid4().hex
        hashed = await asyncio.to_thread(auth.hash_password, password)
        try:
            with database() as db:
                db.execute("INSERT INTO users (id,username,name,password) VALUES (?,?,?,?)", (user_id, username, name, hashed))
                db.execute("INSERT OR REPLACE INTO workspace VALUES ('configured','1')")
        except sqlite3.IntegrityError:
            raise HTTPException(409, "That username already exists.") from None
        return {"id": user_id, "username": username, "name": name, "disabled": False}

    @app.patch("/api/workbench/accounts/{user_id}")
    async def change_account(user_id: str, request: Request):
        body = await request.json()
        password = body.get("password")
        if password is not None and (not isinstance(password, str) or not 10 <= len(password) <= 256):
            raise HTTPException(422, "Use a password of at least 10 characters.")
        hashed = await asyncio.to_thread(auth.hash_password, password) if password is not None else None
        with database() as db:
            if not db.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone():
                raise HTTPException(404, "Account not found.")
            if hashed:
                db.execute("UPDATE users SET password=? WHERE id=?", (hashed, user_id))
            if "disabled" in body:
                db.execute("UPDATE users SET disabled=? WHERE id=?", (int(bool(body["disabled"])), user_id))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        return {"ok": True}

    @app.get("/api/workbench/projects/{pid}/members")
    def members(pid: str):
        p = project(pid)
        with database() as db:
            rows = [dict(r) for r in db.execute("SELECT u.id,u.username,u.name,u.disabled,m.role FROM members m JOIN users u ON u.id=m.user_id WHERE project_id=? ORDER BY u.username", (pid,))]
        return {"owner_id": p.state.get("owner_id", "device"), "members": rows}

    @app.put("/api/workbench/projects/{pid}/members/{user_id}")
    async def put_member(pid: str, user_id: str, request: Request):
        p = project(pid)
        role = _role((await request.json()).get("role"))
        with database() as db:
            if not db.execute("SELECT id FROM users WHERE id=? AND disabled=0", (user_id,)).fetchone():
                raise HTTPException(404, "Active account not found.")
            db.execute("INSERT OR REPLACE INTO members VALUES (?,?,?)", (pid, user_id, role))
        p.emit({"type": "access_changed"})
        return {"role": role}

    @app.delete("/api/workbench/projects/{pid}/members/{user_id}")
    def remove_member(pid: str, user_id: str):
        p = project(pid)
        with database() as db:
            db.execute("DELETE FROM members WHERE project_id=? AND user_id=?", (pid, user_id))
        p.emit({"type": "access_changed"})
        return {"ok": True}

    @app.get("/api/workbench/projects/{pid}/shares")
    def shares(pid: str):
        project(pid)
        with database() as db:
            return {"shares": [dict(r) for r in db.execute("SELECT id,role,label,expires,revoked FROM shares WHERE project_id=? ORDER BY expires DESC", (pid,))]}

    @app.post("/api/workbench/projects/{pid}/shares", status_code=201)
    async def create_share(pid: str, request: Request):
        project(pid)
        body = await request.json()
        role = _role(body.get("role", "viewer"))
        label = str(body.get("label") or "Guest reviewer").strip()[:80]
        try:
            days = int(body.get("days", 30))
        except (ValueError, TypeError):
            raise HTTPException(422, "Choose 1–365 days.") from None
        if not 1 <= days <= 365:
            raise HTTPException(422, "Choose 1–365 days.")
        token, share_id, expires = "wbs_" + secrets.token_urlsafe(32), uuid.uuid4().hex, time.time() + days * 86400
        with database() as db:
            db.execute("INSERT INTO shares (id,project_id,hash,role,label,expires) VALUES (?,?,?,?,?,?)", (share_id, pid, token_hash(token), role, label, expires))
            db.execute("INSERT OR REPLACE INTO workspace VALUES ('configured','1')")
        return {"id": share_id, "role": role, "label": label, "expires": expires, "path": "/#share=" + token}

    @app.delete("/api/workbench/projects/{pid}/shares/{share_id}")
    def revoke_share(pid: str, share_id: str):
        p = project(pid)
        with database() as db:
            db.execute("UPDATE shares SET revoked=1 WHERE id=? AND project_id=?", (share_id, pid))
        p.emit({"type": "access_changed"})
        return {"ok": True}

    @app.get("/api/workbench/projects/{pid}/comments")
    def comments(pid: str):
        project(pid)
        with database() as db:
            return {"comments": [_comment(r) for r in db.execute("SELECT * FROM comments WHERE project_id=? ORDER BY created,id", (pid,))]}

    @app.post("/api/workbench/projects/{pid}/comments", status_code=201)
    async def add_comment(pid: str, request: Request):
        p, body, actor = project(pid), await request.json(), identity(request.scope)
        text = str(body.get("text") or "").strip()
        anchor = body.get("anchor") or {}
        if not text or len(text) > 20_000 or not isinstance(anchor, dict) or set(anchor) - {"view", "ref", "net", "x", "y", "z"}:
            raise HTTPException(422, "Write a comment of 1–20,000 characters with a valid anchor.")
        if any(k in anchor and (not isinstance(anchor[k], str) or len(anchor[k]) > 100) for k in ("view", "ref", "net")) or any(k in anchor and (not isinstance(anchor[k], (int, float)) or not math.isfinite(anchor[k]) or abs(anchor[k]) > 1_000_000) for k in ("x", "y", "z")):
            raise HTTPException(422, "Comment anchors need bounded text and finite coordinates.")
        if anchor.get("ref") and anchor["ref"] not in {c["ref"] for c in (p.state.get("spec") or {}).get("components", [])}:
            raise HTTPException(422, "Choose a component in this design.")
        parent, comment_id, now = body.get("parent_id"), uuid.uuid4().hex, time.time()
        with database() as db:
            if parent and not db.execute("SELECT id FROM comments WHERE id=? AND project_id=? AND parent_id IS NULL", (parent, pid)).fetchone():
                raise HTTPException(404, "Review thread not found.")
            db.execute("INSERT INTO comments VALUES (?,?,?,?,?,?,?,?,?,?)", (comment_id, pid, actor["id"], actor["name"], text, json.dumps(anchor), parent, 0, now, now))
            row = db.execute("SELECT * FROM comments WHERE id=?", (comment_id,)).fetchone()
        p.emit({"type": "comments_changed", "comment_id": comment_id})
        return _comment(row)

    @app.patch("/api/workbench/projects/{pid}/comments/{comment_id}")
    async def change_comment(pid: str, comment_id: str, request: Request):
        p, body, actor = project(pid), await request.json(), identity(request.scope)
        with database() as db:
            row = db.execute("SELECT * FROM comments WHERE id=? AND project_id=?", (comment_id, pid)).fetchone()
            if not row:
                raise HTTPException(404, "Comment not found.")
            if "text" in body and row["author_id"] != actor["id"] and not actor["admin"]:
                raise HTTPException(403, "Only the author can edit this comment.")
            if "resolved" in body and row["author_id"] != actor["id"] and ROLES.get(project_role(actor, p), 0) < 30:
                raise HTTPException(403, "Only the author or an editor can resolve this thread.")
            if "text" in body:
                text = str(body["text"]).strip()
                if not text or len(text) > 20_000:
                    raise HTTPException(422, "Write 1–20,000 characters.")
                db.execute("UPDATE comments SET text=?,updated=? WHERE id=?", (text, time.time(), comment_id))
            if "resolved" in body:
                db.execute("UPDATE comments SET resolved=?,updated=? WHERE id=?", (int(bool(body["resolved"])), time.time(), comment_id))
            changed = db.execute("SELECT * FROM comments WHERE id=?", (comment_id,)).fetchone()
        p.emit({"type": "comments_changed", "comment_id": comment_id})
        return _comment(changed)

    @app.delete("/api/workbench/projects/{pid}/comments/{comment_id}")
    def remove_comment(pid: str, comment_id: str, request: Request):
        p, actor = project(pid), identity(request.scope)
        with database() as db:
            row = db.execute("SELECT * FROM comments WHERE id=? AND project_id=?", (comment_id, pid)).fetchone()
            if not row:
                raise HTTPException(404, "Comment not found.")
            if row["author_id"] != actor["id"] and ROLES.get(project_role(actor, p), 0) < 40:
                raise HTTPException(403, "Only the author or project owner can remove this comment.")
            db.execute("DELETE FROM comments WHERE id=? OR (parent_id=? AND project_id=?)", (comment_id, comment_id, pid))
        p.emit({"type": "comments_changed", "comment_id": comment_id})
        return {"ok": True}
