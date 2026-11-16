"""Private immutable production packages and evidence-labelled RFQ records."""
from __future__ import annotations

import copy
import csv
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import time
import uuid
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from fastapi import HTTPException

from . import suppliers
from .. import design_identity

ROLE_SUFFIXES = {
    "gerbers": {".zip"}, "bom": {".csv", ".xls", ".xlsx"}, "cpl": {".csv", ".xls", ".xlsx"},
    "enclosure": {".step", ".stp", ".stl", ".3mf", ".dxf"},
    "firmware": {".bin", ".hex", ".uf2", ".zip", ".elf"},
    "test_plan": {".md", ".txt", ".pdf"}, "assembly": {".md", ".pdf", ".html", ".png"},
    "other": {".pdf", ".md", ".txt"},
}
REQUIRED = {"pcb": {"gerbers"}, "pcba": {"gerbers", "bom", "cpl"},
            "device": {"gerbers", "bom", "cpl", "enclosure", "test_plan"}}
STAGES = ["accepted", "engineering_review", "materials", "production", "testing", "shipped", "delivered"]
TERMINAL = {"delivered", "cancelled", "declined"}
MAX_FILE = 25_000_000
MAX_PACKAGE = 100_000_000


def digest(value):
    try:
        return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
    except (ValueError, TypeError):
        raise HTTPException(422, "Use JSON values with finite numbers.") from None


def text(value, name, limit=10000, required=False):
    if value is None and not required:
        return ""
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise HTTPException(422, f"{name} must be {'non-empty ' if required else ''}text of at most {limit} characters.")
    return value.strip()


def integer(value, name, low=1, high=100000):
    if type(value) is not int or not low <= value <= high:
        raise HTTPException(422, f"{name} must be a whole number from {low} to {high}.")
    return value


def money(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise HTTPException(422, "Amounts must be finite nonnegative numbers.")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > 100_000_000:
            raise InvalidOperation()
        return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        raise HTTPException(422, "Amounts must be finite nonnegative numbers below 100,000,000.") from None


def currency(value):
    value = value or "USD"
    if not isinstance(value, str) or value not in {"USD", "CNY", "EUR", "GBP", "CAD", "AUD", "JPY"}:
        raise HTTPException(422, "Choose a supported currency code.")
    return value


def private_root(p):
    folder = p.root / ".production"
    if folder.is_symlink() or folder.exists() and not folder.is_dir():
        raise HTTPException(409, "The private production store is not a regular directory.")
    folder.mkdir(mode=0o700, exist_ok=True)
    return folder


def load(p):
    folder = p.root / ".production"
    if folder.is_symlink():
        raise HTTPException(409, "Invalid production store.")
    path = folder / "records.json"
    if not path.exists():
        return {"packages": {}, "rfqs": {}, "estimates": {}, "requests": {}}
    if path.is_symlink():
        raise HTTPException(409, "Invalid production store.")
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or any(not isinstance(data.get(k), dict) for k in ("packages", "rfqs", "estimates", "requests")):
            raise ValueError()
        return data
    except (OSError, ValueError):
        raise HTTPException(409, "Production records could not be read; existing records were preserved.") from None


def save(p, data):
    folder = private_root(p)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(folder / "records.json")


def public(record):
    return {k: copy.deepcopy(v) for k, v in record.items() if k not in {"token_hash", "archive_path", "request_hash"}}


def replay(data, operation, body):
    key = body.get("idempotency_key")
    if key is not None:
        text(key, "Idempotency key", 128, required=True)
    previous = data["requests"].get(f"{operation}:{key}") if key else None
    if previous:
        if previous["hash"] != digest(body):
            raise HTTPException(409, "This idempotency key was already used with a different request.")
        return copy.deepcopy(previous["result"])
    return None


def mutation(p, operation, body, action):
    key = body.get("idempotency_key")
    with p.lock:
        data = load(p)
        cached = replay(data, operation, body)
        if cached is not None:
            return cached
        request_key = f"{operation}:{key}" if key else None
        signature = digest(body)
        result = action(data)
        if request_key:
            # Capability secrets are returned once, never persisted in a replay cache.
            data["requests"][request_key] = {"hash": signature, "result": {k: v for k, v in result.items() if k != "supplier_url"}}
        save(p, data)
        return result


def version(p, base):
    current = (p.state.get("workbench") or {}).get("version", 0)
    if type(base) is not int or base != current:
        raise HTTPException(409, "The saved design changed. Reload before preparing production.")
    if p.engine_busy or p.worker and p.worker.is_alive():
        raise HTTPException(409, "Wait for the current design operation to finish.")
    if not isinstance(p.state.get("spec"), dict):
        raise HTTPException(409, "Save a design before preparing production.")
    return current


def source_file(p, relative, role):
    relative = text(relative, "Project file path", 1024, required=True)
    rel = Path(relative)
    if not isinstance(role, str) or role not in ROLE_SUFFIXES or rel.suffix.lower() not in ROLE_SUFFIXES[role]:
        raise HTTPException(422, "File role and extension do not match a production document type.")
    protected = {"state.json", "events.jsonl", "design.json", "config.json", "credentials.json", "auth.json"}
    if rel.is_absolute() or "\\" in relative or any(s in {"..", "."} or s.startswith(".") for s in rel.parts) \
            or rel.parts[0].lower() == "history" or rel.name.lower() in protected:
        raise HTTPException(422, "Choose a regular visible manufacturing file inside this project.")
    path = p.root / rel
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent != p.root.parent) \
            or not path.resolve().is_relative_to(p.root.resolve()) or not path.is_file():
        raise HTTPException(422, "The source must be a regular project file, not a symlink.")
    if path.stat().st_size > MAX_FILE:
        raise HTTPException(422, "Each production file must be at most 25 MB.")
    return path


def available_files(p):
    rows = []
    for directory, folders, names in os.walk(p.root, followlinks=False):
        parent = Path(directory)
        folders[:] = sorted(f for f in folders if not f.startswith(".") and f != "history" and not (parent / f).is_symlink())
        for name in sorted(names):
            low = name.lower()
            role = ("gerbers" if "gerber" in low and low.endswith(".zip") else
                    "bom" if "bom" in low and Path(low).suffix in ROLE_SUFFIXES["bom"] else
                    "cpl" if any(word in low for word in ("cpl", "-pos")) and low.endswith(".csv") else
                    "enclosure" if Path(low).suffix in ROLE_SUFFIXES["enclosure"] else
                    "firmware" if Path(low).suffix in {".bin", ".hex", ".uf2"} else
                    "test_plan" if any(word in low for word in ("test", "bringup", "bring-up")) and Path(low).suffix in ROLE_SUFFIXES["test_plan"] else None)
            if role:
                relative = (parent / name).relative_to(p.root).as_posix()
                try:
                    path = source_file(p, relative, role)
                    rows.append({"path": relative, "role": role, "size": path.stat().st_size})
                except HTTPException:
                    continue
            if len(rows) >= 500:
                return rows
    return rows


def native_source(p):
    native = p.state.get("workbench_native") or {}
    path = Path(native.get("pcb") or "")
    if design_identity.matches(native,p.state.get('spec')) and path.is_file() and path.resolve().is_relative_to(p.root.resolve()) and not path.is_symlink() \
            and native.get("geometry_pcb_sha256") == hashlib.sha256(path.read_bytes()).hexdigest():
        return path
    return None


def export_native(p, staging, spec):
    from .. import design
    from ..kicad import cli
    pcb = native_source(p)
    if not pcb:
        raise HTTPException(409, "Generate native files for the current saved design in the editor, or select reviewed manufacturing files.")
    native_hash = p.state["workbench_native"]["geometry_pcb_sha256"]
    content = pcb.read_bytes()
    if hashlib.sha256(content).hexdigest() != native_hash:
        raise HTTPException(409, "The native PCB changed before its manufacturing snapshot was copied.")
    staging.mkdir(parents=True, exist_ok=True)
    frozen_pcb = staging / pcb.name
    frozen_pcb.write_bytes(content)
    fab = cli.export_fab(frozen_pcb, staging / "fab", int(spec["board"]["layers"]))
    rows = [("gerbers", Path(fab["gerber_zip"]))]
    bom = staging / "board-bom.csv"
    assembly_parts = [part for part in spec.get("components", [])
                      if not part.get("dnp") and not part.get("terminal") and not design.copper_only(part.get("footprint"))]
    assembly_refs = {part["ref"] for part in assembly_parts}
    # Include MPN and manufacturer for vendor-neutral assembly inquiries.
    with bom.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Designator", "Quantity", "Comment", "Footprint", "LCSC Part #", "MPN", "Manufacturer"])
        for part in assembly_parts:
            cell = lambda v: "'" + str(v) if str(v or "").lstrip().startswith(("=", "+", "-", "@")) else str(v or "")
            writer.writerow([cell(part.get("ref")), 1, cell(part.get("value")), cell(part.get("footprint")),
                             cell(part.get("lcsc")), cell(part.get("mpn")), cell(part.get("manufacturer"))])
    rows.append(("bom", bom))
    if fab.get("pos"):
        # Native placement exports can contain test pads and mechanical features.
        # Keep the exact same assembly references in both vendors' placement files.
        positions = Path(fab["pos"])
        raw = staging / "board-kicad-pos.csv"
        with positions.open(newline="") as incoming, raw.open("w", newline="") as outgoing:
            reader = csv.DictReader(incoming)
            writer = csv.DictWriter(outgoing, fieldnames=reader.fieldnames or [])
            writer.writeheader()
            writer.writerows(row for row in reader if row.get("Ref") in assembly_refs)
        rows.append(("cpl", raw))
        overrides = {c["ref"]: c["cpl"] for c in spec.get("components", []) if isinstance(c.get("cpl"), dict)}
        adjusted, _ = cli.jlc_cpl(raw, staging / "board-jlc-cpl.csv", overrides=overrides)
        rows.append(("cpl", adjusted))
    return rows


def create_package(p, body):
    def action(data):
        current = version(p, body.get("base_version"))
        spec = copy.deepcopy(p.state["spec"])
        scope = body.get("scope", "pcba")
        if not isinstance(scope, str) or scope not in REQUIRED:
            raise HTTPException(422, "Choose PCB, PCBA or complete device scope.")
        quantity = integer(body.get("quantity", 5), "Quantity")
        selected = body.get("files") or []
        if not isinstance(selected, list) or len(selected) > 100 or any(not isinstance(row, dict) for row in selected):
            raise HTTPException(422, "Choose at most 100 production files.")
        if selected and body.get("files_match_design") is not True:
            raise HTTPException(422, "Confirm that the selected files match this saved design version.")
        notes = text(body.get("notes"), "Production notes")
        plan = text(body.get("test_plan"), "Functional test plan", 30000)
        identifier = uuid.uuid4().hex
        directory = private_root(p) / "packages"
        directory.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory, prefix="pending-") as temporary:
            staging = Path(temporary)
            if selected:
                sources = [(row.get("role"), source_file(p, row.get("path"), row.get("role"))) for row in selected]
            else:
                try:
                    sources = export_native(p, staging / "export", spec)
                except (OSError, RuntimeError) as error:
                    raise HTTPException(422, f"Manufacturing export failed: {type(error).__name__}.") from None
            if plan:
                plan_file = staging / "functional-test-plan.md"
                plan_file.write_text(plan)
                sources.append(("test_plan", plan_file))
            payloads, files, total, names = {}, [], 0, set()
            for role, path in sources:
                content = path.read_bytes()
                total += len(content)
                if len(content) > MAX_FILE or total > MAX_PACKAGE:
                    raise HTTPException(422, "Production package exceeds the 100 MB total or 25 MB per-file limit.")
                name = path.name
                serial = 1
                while name.casefold() in names:
                    name = f"{serial}-{path.name}"
                    serial += 1
                names.add(name.casefold())
                archive_path = "files/" + name
                payloads[archive_path] = content
                source = path.relative_to(p.root).as_posix() if path.is_relative_to(p.root) and not path.is_relative_to(staging) else "native_export"
                files.append({"path": source, "archive_path": archive_path, "name": name, "role": role,
                              "size": len(content), "sha256": hashlib.sha256(content).hexdigest()})
            roles = {f["role"] for f in files}
            missing = sorted(REQUIRED[scope] - roles)
            check = p.state.get("workbench_checks") or {}
            checks = copy.deepcopy(check) if design_identity.matches(check,spec) else {"status": "unknown_or_stale"}
            manifest = {"id": identifier, "source_version": current, "spec_sha256": digest(spec),
                        "scope": scope, "quantity": quantity, "created_at": time.time(), "files": files,
                        "missing_roles": missing, "readiness": "incomplete" if missing else "ready_for_supplier_review",
                        "checks": checks, "manufacturing_ready": False, "notes": notes,
                        "provenance": "user_attested_files" if selected else "current_native_export",
                        "review_note": "Supplier DFM/DFA and functional testing are still required; file completeness is not engineering acceptance."}
            output = staging / "package.zip"
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, content in payloads.items():
                    archive.writestr(name, content)
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                archive.writestr("design-spec.json", json.dumps(spec, ensure_ascii=False, indent=2))
            archive_hash = hashlib.sha256(output.read_bytes()).hexdigest()
            target = directory / (identifier + ".zip")
            output.replace(target)
            record = {**manifest, "archive_sha256": archive_hash,
                      "archive_path": target.relative_to(p.root).as_posix(),
                      "download_url": f"/api/projects/{p.id}/production/packages/{identifier}/download"}
        data["packages"][identifier] = record
        return public(record)
    return mutation(p, "package", body, action)


def get_record(data, collection, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise HTTPException(422, "Use a valid production record ID.")
    record = data[collection].get(identifier)
    if not record:
        raise HTTPException(404, "Production record not found.")
    return record


def archive_bytes(p, package):
    path = p.root / package["archive_path"]
    if path.is_symlink() or not path.resolve().is_relative_to(private_root(p).resolve()) or not path.is_file():
        raise HTTPException(409, "The frozen production archive is unavailable.")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != package["archive_sha256"]:
        raise HTTPException(409, "The frozen production archive changed; download was refused.")
    return content


def event(rfq, status, note, source, **extra):
    rfq["revision"] += 1
    rfq["status"] = status
    rfq["updated_at"] = time.time()
    rfq["events"].append({"id": uuid.uuid4().hex, "status": status, "note": note, "source": source,
                          "created_at": rfq["updated_at"], **extra})


def supplier_profile(identifier):
    profile = next((row for row in suppliers.profiles() if row["id"] == identifier), None)
    if not profile:
        raise HTTPException(422, "Choose JLCPCB or PCBWay.")
    return profile


def issue_invite(rfq):
    token = secrets.token_urlsafe(32)
    rfq["token_hash"] = hashlib.sha256(token.encode()).hexdigest()
    rfq["invite_expires_at"] = time.time() + 7 * 86400
    rfq["invite_revoked"] = False
    return f"/production/supplier/{token}"


def create_rfq(p, body):
    def action(data):
        package = get_record(data, "packages", body.get("package_id"))
        archive_bytes(p, package)
        if package["missing_roles"]:
            raise HTTPException(409, "The package is missing required manufacturing files: " + ", ".join(package["missing_roles"]))
        profile = supplier_profile(body.get("supplier_id"))
        estimate_id = body.get("estimate_id")
        if estimate_id:
            estimate = get_record(data, "estimates", estimate_id)
            if estimate["spec_sha256"] != package["spec_sha256"] or estimate["quantity"] != package["quantity"] or estimate.get("scope") != package["scope"]:
                raise HTTPException(409, "Choose an estimate for this frozen design, production scope and batch quantity.")
        target = body.get("target_budget")
        identifier = uuid.uuid4().hex
        record = {"id": identifier, "package_id": package["id"], "supplier_id": profile["id"],
                  "estimate_id": estimate_id, "quantity": package["quantity"], "scope": package["scope"],
                  "target_budget": money(target) if target is not None else None,
                  "currency": currency(body.get("currency")), "notes": text(body.get("notes"), "Inquiry notes"),
                  "contact_email": text(body.get("contact_email"), "Supplier email", 254),
                  "created_at": time.time(), "revision": 0, "quotes": [], "events": [],
                  "accepted_quote_id": None, "external_reference": ""}
        if record["contact_email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", record["contact_email"]):
            raise HTTPException(422, "Enter a supplier email address.")
        record["handoff"] = suppliers.prepare_handoff(profile["id"], record, public(package))
        url = issue_invite(record)
        event(record, "prepared", "Production inquiry prepared. It has not been sent to the factory.", "workspace")
        data["rfqs"][identifier] = record
        return {**public(record), "supplier_url": url}
    return mutation(p, "rfq", body, action)


def revision(rfq, body):
    supplied = body.get("base_revision")
    if supplied is not None and (type(supplied) is not int or supplied != rfq["revision"]):
        raise HTTPException(409, "This inquiry changed. Reload before submitting your response.")


def update_rfq(p, identifier, operation, body):
    def action(data):
        rfq = get_record(data, "rfqs", identifier)
        revision(rfq, body)
        if operation == "invite":
            if rfq["status"] in TERMINAL:
                raise HTTPException(409, "This inquiry is closed.")
            url = issue_invite(rfq)
            event(rfq, rfq["status"], "Supplier link rotated; the previous link was revoked.", "workspace")
            return {**public(rfq), "supplier_url": url}
        if operation == "revoke":
            rfq["invite_revoked"] = True
            event(rfq, rfq["status"], "Supplier access revoked.", "workspace")
        elif operation == "submit":
            if body.get("channel") != "manual" or body.get("sent") is not True:
                raise HTTPException(422, "Confirm that you sent the frozen package and link through the supplier's official channel.")
            if rfq["status"] != "prepared":
                raise HTTPException(409, "Only a prepared inquiry can be marked as sent.")
            reference = text(body.get("external_reference"), "External handoff reference", 1000, required=True)
            rfq["external_reference"] = reference
            event(rfq, "submitted", text(body.get("notes"), "Handoff notes") or reference, "buyer_recorded_handoff")
        elif operation == "accept":
            if rfq["status"] != "quoted":
                raise HTTPException(409, "Only a current supplier quote can be accepted.")
            quote = next((q for q in rfq["quotes"] if q["id"] == body.get("quote_id")), None)
            if not quote or quote is not rfq["quotes"][-1]:
                raise HTTPException(409, "Accept the supplier's latest quote.")
            if date.fromisoformat(quote["valid_until"]) < datetime.now(timezone.utc).date():
                raise HTTPException(409, "This quote expired. Request a new supplier quote.")
            rfq["accepted_quote_id"] = quote["id"]
            event(rfq, "accepted", "Buyer accepted this quote. No payment or factory purchase order was sent.", "buyer")
        elif operation == "sync":
            try:
                suppliers.sync_order(rfq["supplier_id"], public(rfq))
            except suppliers.SupplierSetupError as error:
                raise HTTPException(409, str(error)) from None
        else:
            raise HTTPException(404, "Unknown production action.")
        return public(rfq)
    return mutation(p, f"rfq:{identifier}:{operation}", body, action)


def find_invite(manager, token):
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,64}", token):
        raise HTTPException(404, "Supplier link is invalid, expired or revoked.")
    hashed = hashlib.sha256(token.encode()).hexdigest()
    for p in list(manager.projects.values()):
        with p.lock:
            for rfq in load(p)["rfqs"].values():
                if hmac.compare_digest(rfq.get("token_hash", ""), hashed) and not rfq.get("invite_revoked") and rfq.get("invite_expires_at", 0) > time.time():
                    return p, rfq["id"]
    raise HTTPException(404, "Supplier link is invalid, expired or revoked.")


def supplier_reply(p, identifier, operation, body):
    def action(data):
        rfq = get_record(data, "rfqs", identifier)
        revision(rfq, body)
        if operation == "quote":
            if rfq["status"] not in {"prepared", "submitted", "quoted"}:
                raise HTTPException(409, "This inquiry can no longer receive quotes.")
            if body.get("decision") == "decline":
                event(rfq, "declined", text(body.get("notes"), "Reason", required=True), "supplier_portal", identity_verified=False)
                return public(rfq)
            if body.get("decision") != "quote":
                raise HTTPException(422, "Choose quote or decline.")
            lines = body.get("line_items")
            if not isinstance(lines, list) or not 1 <= len(lines) <= 40 or any(not isinstance(line, dict) for line in lines):
                raise HTTPException(422, "Provide between 1 and 40 quote line items.")
            items = [{"item": text(line.get("item"), "Line item", 200, required=True), "amount": money(line.get("amount"))} for line in lines]
            valid_until = body.get("valid_until")
            try:
                expires = date.fromisoformat(valid_until)
                if expires < datetime.now(timezone.utc).date():
                    raise ValueError()
            except (ValueError, TypeError):
                raise HTTPException(422, "Use an unexpired quote date in YYYY-MM-DD format.") from None
            quote = {"id": uuid.uuid4().hex, "supplier_name": text(body.get("supplier_name"), "Supplier name", 200, True),
                     "contact_name": text(body.get("contact_name"), "Contact name", 200, True),
                     "reference": text(body.get("reference"), "Quote reference", 200, True),
                     "currency": currency(body.get("currency")), "line_items": items,
                     "total": float(sum(Decimal(str(line["amount"])) for line in items)),
                     "quantity": rfq["quantity"], "lead_time_days": integer(body.get("lead_time_days"), "Lead time", 1, 730),
                     "valid_until": expires.isoformat(), "notes": text(body.get("notes"), "Quote notes"),
                     "source": "supplier_portal", "identity_verified": False, "created_at": time.time()}
            rfq["quotes"].append(quote)
            event(rfq, "quoted", "Supplier link holder submitted quote " + quote["reference"], "supplier_portal", identity_verified=False)
        elif operation == "events":
            status = body.get("status")
            if not rfq.get("accepted_quote_id") or rfq["status"] in TERMINAL:
                raise HTTPException(409, "Production updates require an accepted quote and an open inquiry.")
            previous = rfq.get("resume_status", rfq["status"]) if rfq["status"] == "on_hold" else rfq["status"]
            if status not in STAGES[1:] + ["on_hold", "cancelled"]:
                raise HTTPException(422, "Choose a supported production stage.")
            if status in STAGES and STAGES.index(status) < STAGES.index(previous):
                raise HTTPException(409, "Production cannot silently move to an earlier stage.")
            note = text(body.get("note"), "Progress note", 10000, required=True)
            if status == "on_hold":
                rfq["resume_status"] = previous
            else:
                rfq.pop("resume_status", None)
            event(rfq, status, note, "supplier_portal", identity_verified=False,
                  tracking_number=text(body.get("tracking_number"), "Tracking number", 200),
                  carrier=text(body.get("carrier"), "Carrier", 100))
        else:
            raise HTTPException(404, "Unknown supplier action.")
        return public(rfq)
    return mutation(p, f"supplier:{identifier}:{operation}", body, action)
