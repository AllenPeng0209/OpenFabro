"""Verified supplier metadata and explicit, non-transmitting RFQ handoffs.

The published partner pages are not enough to authenticate production requests.
Until an approved account and its protocol have been verified, this module never
submits files, spends money, or invents an external order receipt.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
import re


_REQUIRED_ROLES = {
    "pcb": ["gerbers"],
    "pcba": ["gerbers", "bom", "cpl"],
    "device": ["gerbers", "bom", "cpl", "enclosure", "test_plan"],
}

_PROFILES = {
    "jlcpcb": {
        "id": "jlcpcb",
        "name": "嘉立创 / JLCPCB",
        "mode": "manual_handoff",
        "api_available": False,
        "api_status": "partner_setup_required",
        "api_notes": (
            "JLCAPI access must be applied for and the approved account's production "
            "authentication and PCBA scope verified. Use the manual handoff and supplier portal."
        ),
        "quote_url": "https://cart.jlcpcb.com/quote",
        "api_docs_url": "https://api.jlcpcb.com/",
        "requirements_url": "https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad",
        "capabilities": ["pcb", "pcba"],
        "file_requirements": [
            {"role": "gerbers", "formats": ["zip"],
             "instructions": "Include copper, solder mask, silkscreen, paste and drill outputs for the selected board."},
            {"role": "bom", "formats": ["csv", "xls", "xlsx"],
             "instructions": "Use Comment, Designator, Footprint and JLCPCB / LCSC Part #; confirm matched parts and stock."},
            {"role": "cpl", "formats": ["csv", "xls", "xlsx"],
             "instructions": "Use Designator, Mid X, Mid Y, Rotation and Layer; coordinates in mm. Verify rotations in JLCPCB's placement preview."},
        ],
    },
    "pcbway": {
        "id": "pcbway",
        "name": "PCBWay",
        "mode": "manual_handoff",
        "api_available": False,
        "api_status": "partner_setup_required",
        "api_notes": (
            "Public PCBWay partner documentation labels its endpoint a test environment; "
            "production authentication and access must be agreed with PCBWay. "
            "Use the manual handoff and supplier portal."
        ),
        "quote_url": "https://www.pcbway.com/pcb-assembly.html",
        "api_docs_url": "https://api-partner.pcbway.com/Help",
        "requirements_url": "https://www.pcbway.com/assembly-file-requirements.html",
        "capabilities": ["pcb", "pcba"],
        "file_requirements": [
            {"role": "gerbers", "formats": ["zip"],
             "instructions": "Include RS-274X copper, silkscreen, paste and drill outputs for the selected board."},
            {"role": "bom", "formats": ["csv", "xls", "xlsx"],
             "instructions": "Include references, quantity per board, package, description, manufacturer and manufacturer part number (MPN) for turnkey sourcing."},
            {"role": "cpl", "formats": ["csv", "xls", "xlsx", "txt", "pos"],
             "instructions": "Include reference, X/Y in mm, rotation and board side for SMT parts. References must match BOM and silkscreen."},
            {"role": "assembly", "formats": ["pdf", "png", "jpg", "html"],
             "instructions": "Provide an assembly drawing where designators, pin 1 or polarity are unclear in the silkscreen."},
        ],
    },
}


class SupplierSetupError(ValueError):
    """A real factory connection has not yet been verified for this supplier."""

    def __init__(self, supplier_id: str):
        profile = _profile(supplier_id)
        self.supplier_id = supplier_id
        self.docs_url = profile["api_docs_url"]
        super().__init__(profile["api_notes"])


def _profile(supplier_id: str) -> dict:
    if not isinstance(supplier_id, str) or supplier_id not in _PROFILES:
        raise ValueError("Unsupported supplier. Choose JLCPCB or PCBWay.")
    return _PROFILES[supplier_id]


def profiles() -> list[dict]:
    """Public connection state, never credentials or remote receipt claims."""
    return deepcopy(list(_PROFILES.values()))


def _upload_files(files) -> list[dict]:
    if not isinstance(files, list):
        raise ValueError("Package files must be a list.")
    result = []
    for row in files:
        if not isinstance(row, dict) or not isinstance(row.get("role"), str):
            raise ValueError("Each package file needs a role and relative path.")
        value = row.get("archive_path") or row.get("path")
        if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
            raise ValueError("Package file path must be a safe relative path.")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part.startswith(".") for part in value.split("/")):
            raise ValueError("Package file path must be a safe relative path.")
        item = {"role": row["role"], "path": value, "name": path.name}
        if isinstance(row.get("sha256"), str) and re.fullmatch(r"[a-fA-F0-9]{64}", row["sha256"]):
            item["sha256"] = row["sha256"]
        result.append(item)
    return result


def prepare_handoff(supplier_id: str, rfq: dict, package: dict) -> dict:
    """Return exact upload instructions; no supplier has received anything yet.

    The caller owns the immutable ZIP and access-controlled supplier link. A
    complete file-role list is a checklist, not validation of file contents or a
    supplier's agreement to manufacture a functioning device.
    """
    profile = _profile(supplier_id)
    if not isinstance(rfq, dict) or not isinstance(package, dict):
        raise ValueError("An RFQ and frozen package are required.")
    if not package.get("id") or rfq.get("package_id") != package["id"]:
        raise ValueError("The RFQ must reference this exact frozen package.")
    if rfq.get("supplier_id", supplier_id) != supplier_id:
        raise ValueError("The RFQ belongs to another supplier.")
    scope = package.get("scope")
    if not isinstance(scope, str) or scope not in _REQUIRED_ROLES:
        raise ValueError("Package scope must be pcb, pcba or device.")
    quantity = package.get("quantity")
    if type(quantity) is not int or not 1 <= quantity <= 100_000:
        raise ValueError("Package quantity must be a whole number from 1 to 100,000.")
    upload_files = _upload_files(package.get("files"))
    roles = {row["role"] for row in upload_files}
    required_roles = list(_REQUIRED_ROLES[scope])
    missing = [role for role in required_roles if role not in roles]
    notes = [
        "Download and review the frozen ZIP, then upload the relevant files at the supplier's official quotation page or send its scoped portal link to your supplier contact.",
        "Record a manual submission only after actually sending the files; this handoff has not contacted the factory.",
        "The supplier must review file contents, manufacturability, component sourcing, price, lead time and functional-test scope.",
    ]
    if scope == "device":
        notes.append(
            "These standard channels cover PCB/PCBA. Obtain explicit agreement for enclosure manufacturing, firmware programming, functional testing, final assembly and packaging."
        )
    return {
        "supplier_id": supplier_id,
        "supplier_name": profile["name"],
        "channel": "manual_handoff",
        "status": "prepared",
        "transmitted": False,
        "api_available": False,
        "quote_url": profile["quote_url"] if scope != "pcb" or supplier_id != "pcbway" else "https://www.pcbway.com/orderonline.aspx",
        "package_id": package["id"],
        "package_sha256": package.get("archive_sha256"),
        "scope": scope,
        "quantity": quantity,
        "required_roles": required_roles,
        "missing_roles": missing,
        "files_complete": not missing,
        "needs_scope_confirmation": scope == "device",
        "upload_files": upload_files,
        "file_requirements": deepcopy(profile["file_requirements"]),
        "notes": notes,
    }


def sync_order(supplier_id: str, rfq: dict) -> dict:
    """Fail closed: no verified production authentication is shipped in this MVP.

    Merely setting an environment variable cannot turn an unverified protocol
    into a live integration. Manual supplier-portal events remain usable.
    """
    raise SupplierSetupError(supplier_id)
