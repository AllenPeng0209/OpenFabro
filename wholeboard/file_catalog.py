"""Paged visible project files and exact active native output references."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import quote
from . import design_identity

TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".cpp", ".c", ".h", ".hpp", ".ini", ".scad", ".csv"}
INTERNAL = {"state.json", "events.jsonl"}


def _native_context(root, state, fingerprint):
    native = state.get("workbench_native") or {}
    empty = {"status": "none", "folder": None, "primary_paths": {}, "missing_roles": []}
    if not native:
        return empty

    def relative(value):
        if not isinstance(value, str):
            return None
        path = Path(value).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return None
        rel = path.relative_to(root)
        if not rel.parts or rel.parts[0] != "native" or any(p.startswith(".") for p in rel.parts):
            return None
        return rel.as_posix()

    pcb = relative(native.get("pcb"))
    if not pcb:
        return {**empty, "status": "unavailable"}
    folder = str(Path(pcb).parent)
    primary = {"pcb": pcb}
    values = {"schematic": native.get("sch"), "geometry": native.get("geometry_file") or str(root / folder / "geometry.json")}
    for role, value in values.items():
        rel = relative(value)
        if rel and Path(rel).parent.as_posix() == folder:
            primary[role] = rel
    return {"status": "current" if design_identity.matches(native,state.get('spec')) else "stale",
            "folder": folder, "primary_paths": primary, "fingerprint": native.get("fingerprint"),
            "native_schema": native.get("schema"), "geometry_schema": native.get("geometry_schema"),
            "semantic_fingerprint":native.get('semantic_fingerprint'),"semantic_fingerprint_policy":native.get('semantic_fingerprint_policy'),
            "missing_roles": [role for role in ("pcb", "schematic", "geometry") if role not in primary]}


def listing(project, offset=0, limit=1000, expected_index_sha256=None):
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 2000:
        raise ValueError("Choose a nonnegative file offset and a limit from1 to2000.")
    if expected_index_sha256 is not None and (not isinstance(expected_index_sha256,str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected_index_sha256)):
        raise ValueError("Use a64-character SHA-256 file catalog digest.")
    root = project.root.resolve()
    rows, errors = [], []

    def scan_error(error):
        try:
            path = Path(error.filename).relative_to(root).as_posix()
        except (ValueError, TypeError):
            path = "project files"
        errors.append({"path": path, "error": type(error).__name__})

    with project.lock:
        state = project.state
        version = state.get("workbench", {}).get("version", 0)
        source = hashlib.sha256(json.dumps(state.get("spec"), sort_keys=True).encode()).hexdigest()
        native = _native_context(root, state, source)
        for directory, folders, names in os.walk(root, topdown=True, onerror=scan_error, followlinks=False):
            parent = Path(directory)
            folders[:] = sorted(name for name in folders if not name.startswith(".") and not (parent / name).is_symlink())
            for name in sorted(names):
                path = parent / name
                if name.startswith(".") or path.is_symlink():
                    continue
                try:
                    if not path.is_file() or not path.resolve().is_relative_to(root):
                        continue
                    rel = path.relative_to(root).as_posix()
                    if rel in INTERNAL:
                        continue
                    stat = path.stat()
                    category = "native" if rel.startswith("native/") else "history" if rel.startswith("history/") else "project"
                    editable = rel == "design.json" or category == "project" and not rel.startswith('mechanical/') and path.suffix.lower() in TEXT_SUFFIXES
                    native_status, role = None, None
                    if category == "native":
                        in_current = rel.startswith((native.get("folder") or "\0") + "/")
                        native_status = native["status"] if in_current else "saved"
                        role = next((key for key, value in native["primary_paths"].items() if value == rel), None)
                        if in_current and not role and re.fullmatch(r"geometry(?:-v\d+-[a-f0-9]+)?\.json", name):
                            role = "older_geometry"
                    rows.append({"name": name, "path": rel, "size": stat.st_size,
                                 "url": f"/api/projects/{project.id}/files/{quote(rel, safe='/')}?v={stat.st_mtime_ns}",
                                 "modified_at": stat.st_mtime, "mtime_ns": str(stat.st_mtime_ns),
                                 "category": category, "text_editable": editable and stat.st_size <= 2_000_000,
                                 "native_status": native_status, "native_role": role})
                except OSError as error:
                    scan_error(error)
        rows.sort(key=lambda row: (row["path"].casefold(), row["path"]))
        digest = hashlib.sha256(json.dumps({"files": [(r["path"], r["size"], r["mtime_ns"]) for r in rows],
                                           "design_version": version, "source": source, "native": native},
                                          ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if expected_index_sha256 and expected_index_sha256.lower() != digest:
        raise RuntimeError("The project files or active generation changed. Reload the file catalog from the beginning.")
    if offset > len(rows):
        raise ValueError("The requested file offset is outside the catalog.")
    end = min(offset + limit, len(rows))
    return {"files": rows[offset:end], "total": len(rows), "offset": offset, "next_offset": end,
            "truncated": end < len(rows), "index_sha256": digest, "design_version": version, "native": native,
            "scan_errors": errors[:100], "scan_errors_count": len(errors), "scan_errors_truncated": len(errors) > 100}
