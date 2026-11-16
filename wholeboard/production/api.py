"""Project-authorized buyer routes and a narrowly scoped supplier capability app."""
from __future__ import annotations

import asyncio
import copy
import json
import math
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from .. import collaboration
from . import estimate, service, suppliers

WEB = Path(__file__).parent.parent / "web"
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow"}
_estimate_locks: dict[str, threading.Lock] = {}


def finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError()
    return result


async def body(request):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Send production actions as application/json.")
    content = await request.body()
    if len(content) > 100_000:
        raise HTTPException(413, "Production request is too large.")
    try:
        value = json.loads(content, parse_float=finite_float, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, "Send a valid JSON object with finite numbers.") from None
    if not isinstance(value, dict):
        raise HTTPException(422, "Production actions must be JSON objects.")
    key = request.headers.get("idempotency-key")
    if key:
        value["idempotency_key"] = key
    return value


def page():
    return HTMLResponse((WEB / "production.html").read_text(), headers=PRIVATE_HEADERS)


def download(content, name):
    return Response(content, media_type="application/zip", headers={**PRIVATE_HEADERS,
                    "Content-Disposition": f'attachment; filename="{name}.zip"'})


class SupplierGateway:
    """Expose only the isolated supplier app, never bypass workspace authorization."""
    def __init__(self, app, portal_app):
        self.app, self.portal_app = app, portal_app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        public = path == "/production" or path.startswith(("/production/supplier/", "/api/production/supplier/"))
        asset = path in {"/static/production.html", "/static/production.mjs", "/static/production.css", "/static/workbench-icons.mjs", "/static/icon.svg", "/static/openfabro-mascot.png"} \
            or path.startswith("/static/fonts/") and re.fullmatch(r"/static/fonts/[A-Za-z0-9_.-]+\.(woff2?|ttf)", path)
        if scope["type"] != "http" or not (public or asset):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        origin = headers.get(b"origin", b"").decode("latin1")
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"} and origin and urlsplit(origin).netloc != headers.get(b"host", b"").decode("latin1"):
            return await JSONResponse({"detail": "Use the supplier portal's own page to reply."}, status_code=403, headers=PRIVATE_HEADERS)(scope, receive, send)
        if asset:
            file = WEB / path.removeprefix("/static/")
            response = FileResponse(file, headers={"Cache-Control": "no-cache"}) if file.is_file() else JSONResponse({"detail": "Not found"}, status_code=404)
            return await response(scope, receive, send)
        return await self.portal_app(scope, receive, send)


def attach_production(app: FastAPI, get_manager):
    buyer = APIRouter(tags=["production"])
    portal = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def project(pid):
        p = get_manager().get(pid)
        if p is None:
            raise HTTPException(404, "Project not found.")
        return p

    @portal.get("/production")
    def buyer_shell():
        return page()

    @portal.get("/production/supplier/{token}")
    def supplier_shell(token: str):
        return page()

    @buyer.get("/api/projects/{pid}/production")
    def overview(pid: str, request: Request):
        p = project(pid)
        with p.lock:
            data = service.load(p)
            return {"project": {"id": p.id, "title": p.display_title(), "version": (p.state.get("workbench") or {}).get("version", 0)},
                    "access": collaboration.access(collaboration.identity(request.scope), p),
                    "suppliers": suppliers.profiles(), "packages": [service.public(r) for r in reversed(list(data["packages"].values()))],
                    "estimates": list(reversed(list(data["estimates"].values()))),
                    "rfqs": [service.public(r) for r in reversed(list(data["rfqs"].values()))],
                    "available_files": service.available_files(p), "can_export_native": service.native_source(p) is not None,
                    "ai": estimate.ai_status()}

    def compute_estimate(p, options):
        # Serialize estimates per project while leaving the design lock free during
        # inference. Retries, including concurrent retries, replay before using AI.
        with _estimate_locks.setdefault(str(p.root.resolve()), threading.Lock()):
            with p.lock:
                cached = service.replay(service.load(p), "estimate", options)
                if cached is not None:
                    return cached
                current = service.version(p, options.get("base_version"))
                spec = copy.deepcopy(p.state["spec"])
                quoted = copy.deepcopy(p.state.get("quote"))
                stock = copy.deepcopy(p.state.get("stock"))
                stamp = service.digest(spec)
            result = estimate.build_estimate(spec, options, current_quote=quoted, stock=stock,
                                             ai=options.get("use_ai", True))
            def action(data):
                service.version(p, current)
                if service.digest(p.state["spec"]) != stamp:
                    raise HTTPException(409, "The design changed during estimation. The old estimate was not saved as current.")
                record = {**result, "id": uuid.uuid4().hex, "source_version": current,
                          "spec_sha256": stamp, "created_at": time.time(),
                          "scope": options.get("scope", "pcba" if options.get("assembly", True) else "pcb")}
                data["estimates"][record["id"]] = record
                return record
            return service.mutation(p, "estimate", options, action)

    @buyer.post("/api/projects/{pid}/production/estimates", status_code=201)
    async def make_estimate(pid: str, request: Request):
        options = await body(request)
        if "use_ai" in options and type(options["use_ai"]) is not bool:
            raise HTTPException(422, "Choose whether to run the AI analysis.")
        try:
            return await asyncio.to_thread(compute_estimate, project(pid), options)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @buyer.post("/api/projects/{pid}/production/packages", status_code=201)
    async def make_package(pid: str, request: Request):
        return await asyncio.to_thread(service.create_package, project(pid), await body(request))

    @buyer.get("/api/projects/{pid}/production/packages/{identifier}/download")
    def package_download(pid: str, identifier: str):
        p = project(pid)
        with p.lock:
            record = service.get_record(service.load(p), "packages", identifier)
            return download(service.archive_bytes(p, record), "production-" + identifier)

    @buyer.post("/api/projects/{pid}/production/rfqs", status_code=201)
    async def make_rfq(pid: str, request: Request):
        return service.create_rfq(project(pid), await body(request))

    @buyer.post("/api/projects/{pid}/production/rfqs/{identifier}/{operation}")
    async def rfq_action(pid: str, identifier: str, operation: str, request: Request):
        return service.update_rfq(project(pid), identifier, operation, await body(request))

    @portal.get("/api/production/supplier/{token}")
    def supplier_overview(token: str):
        p, identifier = service.find_invite(get_manager(), token)
        with p.lock:
            data = service.load(p)
            rfq = service.get_record(data, "rfqs", identifier)
            package = service.get_record(data, "packages", rfq["package_id"])
            return JSONResponse({"rfq": service.public(rfq), "package": {k: v for k, v in service.public(package).items() if k != "download_url"},
                                 "supplier": service.supplier_profile(rfq["supplier_id"]), "project_title": p.display_title()}, headers=PRIVATE_HEADERS)

    @portal.get("/api/production/supplier/{token}/package")
    def supplier_package(token: str):
        p, identifier = service.find_invite(get_manager(), token)
        with p.lock:
            data = service.load(p)
            rfq = service.get_record(data, "rfqs", identifier)
            package = service.get_record(data, "packages", rfq["package_id"])
            return download(service.archive_bytes(p, package), "production-" + package["id"])

    @portal.post("/api/production/supplier/{token}/{operation}")
    async def supplier_action(token: str, operation: str, request: Request):
        value = await body(request)
        p, identifier = service.find_invite(get_manager(), token)
        with p.lock:
            # Recheck under the same lock used for the write, including rotation/revocation.
            service.find_invite(get_manager(), token)
            result = service.supplier_reply(p, identifier, operation, value)
            return JSONResponse(result, headers=PRIVATE_HEADERS)

    app.include_router(buyer)
    # Last registered middleware is outermost; public capabilities enter their own app.
    app.add_middleware(SupplierGateway, portal_app=portal)
