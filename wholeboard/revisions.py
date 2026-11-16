"""Revision history: a summary of every build, comparisons between two designs, and restoring one."""
from __future__ import annotations

import json
import re
import time
import hashlib
from pathlib import Path

from .project import Project
from . import design_identity


def _spec(rdir: Path) -> dict | None:
    try:
        return json.loads((rdir / "design.json").read_text())
    except (OSError, ValueError):
        return None


def rev_dirs(p: Project) -> list[tuple[int, Path]]:
    out = []
    for d in p.root.glob("rev*"):
        m = re.fullmatch(r"rev(\d+)", d.name)
        if m and d.is_dir() and (d / "design.json").exists():
            out.append((int(m.group(1)), d))
    return sorted(out)


def record(p: Project, rev: int, result: dict, started: float) -> dict:
    """Write rev<N>/summary.json after a build (successful or not)."""
    rdir = p.root / f"rev{rev}"
    spec = _spec(rdir) or {}
    b = spec.get("board") or {}
    try:
        q = json.loads((rdir / "quote.json").read_text())
    except (OSError, ValueError):
        q = None
    prev = None
    for n, d in reversed(rev_dirs(p)):
        if n < rev:
            prev = _spec(d)
            break
    s = {
        "revision": rev, "time": time.time(), "build_s": round(time.time() - started, 1),
        "ok": bool(result.get("ok")), "stage": result.get("stage"),
        "errors": [str(e) for e in (result.get("errors") or [])][:6],
        "board": {"width_mm": b.get("width_mm"), "height_mm": b.get("height_mm"), "layers": b.get("layers")},
        "parts": len(spec.get("components") or []), "nets": len(spec.get("nets") or []),
        "total": (q or {}).get("total"), "per_board": (q or {}).get("per_board"),
        "image": f"rev{rev}/render-iso.png" if (rdir / "render-iso.png").exists() else None,
        "changes": brief(compare(prev, spec)) if prev else "first design",
        "by": result.get("by") or "",
    }
    ke = result.get("kicad_edits")
    if ke:
        s["kicad_edits"] = {k: ke.get(k) for k in ("hand_placed", "held", "nets", "new")}
    (rdir / "summary.json").write_text(json.dumps(s, indent=1))
    return s


def listing(p: Project) -> list[dict]:
    out = []
    for n, d in rev_dirs(p):
        try:
            s = json.loads((d / "summary.json").read_text())
        except (OSError, ValueError):
            spec = _spec(d) or {}
            s = {"revision": n, "time": (d / "design.json").stat().st_mtime, "ok": None,
                 "parts": len(spec.get("components") or []), "nets": len(spec.get("nets") or []),
                 "board": {k: (spec.get("board") or {}).get(k) for k in ("width_mm", "height_mm", "layers")},
                 "image": f"rev{n}/render-iso.png" if (d / "render-iso.png").exists() else None, "changes": ""}
        s["current"] = n == p.state.get("revision")
        out.append(s)
    return out


def compare(a: dict | None, b: dict | None) -> dict:
    """What changed from design a to design b: parts, values, footprints, LCSC numbers, nets, board."""
    a, b = a or {}, b or {}
    ca = {c["ref"]: c for c in a.get("components") or []}
    cb = {c["ref"]: c for c in b.get("components") or []}
    changed = []
    for r in sorted(set(ca) & set(cb), key=_ref_key):
        diffs = {k: [ca[r].get(k), cb[r].get(k)] for k in ("value", "footprint", "lcsc", "symbol")
                 if (ca[r].get(k) or "") != (cb[r].get(k) or "")}
        pa, pb = ca[r].get("placement") or {}, cb[r].get("placement") or {}
        if pa != pb and (pa or pb):
            diffs["placement"] = [pa or None, pb or None]
        if diffs:
            changed.append({"ref": r, "changes": diffs})
    na = {n["name"]: set(n.get("pins") or []) for n in a.get("nets") or []}
    nb = {n["name"]: set(n.get("pins") or []) for n in b.get("nets") or []}
    net_changes = []
    for n in sorted(set(na) & set(nb)):
        if na[n] != nb[n]:
            net_changes.append({"net": n, "added": sorted(nb[n] - na[n]), "removed": sorted(na[n] - nb[n])})
    ba, bb = a.get("board") or {}, b.get("board") or {}
    board = {k: [ba.get(k), bb.get(k)] for k in sorted(set(ba) | set(bb)) if ba.get(k) != bb.get(k)}
    rules = {k: [(a.get("rules") or {}).get(k), (b.get("rules") or {}).get(k)]
             for k in sorted(set(a.get("rules") or {}) | set(b.get("rules") or {}))
             if (a.get("rules") or {}).get(k) != (b.get("rules") or {}).get(k)}
    return {"parts_added": [_part(cb[r]) for r in sorted(set(cb) - set(ca), key=_ref_key)],
            "parts_removed": [_part(ca[r]) for r in sorted(set(ca) - set(cb), key=_ref_key)],
            "parts_changed": changed,
            "nets_added": [{"net": n, "pins": sorted(nb[n])} for n in sorted(set(nb) - set(na))],
            "nets_removed": [{"net": n, "pins": sorted(na[n])} for n in sorted(set(na) - set(nb))],
            "nets_changed": net_changes, "board": board, "rules": rules,**field_comparison(a,b)}


def field_comparison(a,b,limit=200):
    """Complete JSON comparison, including copper/libraries and unknown future fields."""
    changes=[];representations=[];count=0;representation_count=0;missing=object();values_truncated=False;representation_truncated=False
    def bounded(value):
        nonlocal values_truncated
        encoded=json.dumps(value,ensure_ascii=False)
        if len(encoded)>2000:
            values_truncated=True
            return {'preview':encoded[:2000],'value_truncated':True}
        return value
    def walk(left,right,path):
        nonlocal count,representation_count,representation_truncated
        if isinstance(left,dict) and isinstance(right,dict):
            for key in sorted(left.keys()|right.keys()):walk(left.get(key,missing),right.get(key,missing),path+'/'+str(key).replace('~','~0').replace('/','~1'))
        elif isinstance(left,list) and isinstance(right,list):
            for index in range(max(len(left),len(right))):walk(left[index] if index<len(left) else missing,right[index] if index<len(right) else missing,path+'/'+str(index))
        elif left is not missing and right is not missing and design_identity.equal(left,right):
            if type(left) is not type(right) or json.dumps(left)!=json.dumps(right):
                representation_count+=1
                if len(representations)<limit:representations.append({'path':path or '/','before':left,'after':right,'before_json':json.dumps(left),'after_json':json.dumps(right)})
                else:representation_truncated=True
        else:
            count+=1
            if len(changes)<limit:
                change={'path':path or '/','kind':'added' if left is missing else 'removed' if right is missing else 'changed'}
                if left is not missing:change['before']=bounded(left)
                if right is not missing:change['after']=bounded(right)
                changes.append(change)
    walk(a,b,'')
    keys=sorted(a.keys()|b.keys())
    digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    same={key:key in a and key in b and design_identity.equal(a[key],b[key]) for key in keys}
    serialization_changed=[key for key in keys if key not in a or key not in b or digest(a[key])!=digest(b[key])]
    return {'field_changes':changes,'field_change_count':count,'field_changes_truncated':count>limit or values_truncated,
            'comparison_policy':design_identity.POLICY,
            'representation_changes':representations,'representation_change_count':representation_count,'representation_changes_truncated':representation_truncated,
            'changed_sections':[key for key in keys if not same[key]],
            'unchanged_sections':[key for key in keys if same[key]],
            'serialization_changed_sections':serialization_changed,
            'before_semantic_sha256':design_identity.fingerprint(a),'after_semantic_sha256':design_identity.fingerprint(b),
            'before_sha256':digest(a),'after_sha256':digest(b)}


def design_history(p,arguments):
    """Read only the owning project's design snapshots; never accept file paths."""
    with p.lock:
        current=(p.state.get('workbench') or {}).get('version',0)
        available=sorted(int(match[1]) for path in (p.root/'history').glob('design-v*.json') if (match:=re.fullmatch(r'design-v(\d+)\.json',path.name)) and not path.is_symlink())
        result={'current_version':current,'versions':available}
        if 'from_version' not in arguments:return result
        first,last=arguments['from_version'],arguments.get('to_version',current)
        def read_version(version):
            if type(version) is not int or version<0 or version>10_000_000:raise ValueError('Choose an integer design version from this project history.')
            path=p.root/'history'/f'design-v{version}.json';target=path.resolve()
            if not target.is_relative_to(p.root.resolve()) or path.is_symlink() or not path.is_file() or path.stat().st_size>20_000_000:raise ValueError('Design version not found inside this project, or snapshot is too large.')
            payload=path.read_bytes();data=json.loads(payload)
            if not isinstance(data,dict) or data.get('version')!=version or not isinstance(data.get('spec'),dict):raise ValueError('The design snapshot is invalid.')
            return data['spec'],hashlib.sha256(payload).hexdigest()
        a,from_hash=read_version(first);b,to_hash=read_version(last)
        result.update(from_version=first,to_version=last,from_snapshot_sha256=from_hash,to_snapshot_sha256=to_hash,**compare(a,b))
        return result


def brief(d: dict) -> str:
    """One line for a comparison, e.g. '+2 parts, R3 value 10k → 4k7, board 40 → 45 mm wide'."""
    bits = []
    if d["parts_added"]:
        bits.append(f"+{len(d['parts_added'])} part{'s' if len(d['parts_added']) != 1 else ''} "
                    f"({', '.join(x['ref'] for x in d['parts_added'][:4])})")
    if d["parts_removed"]:
        bits.append(f"−{len(d['parts_removed'])} part{'s' if len(d['parts_removed']) != 1 else ''} "
                    f"({', '.join(x['ref'] for x in d['parts_removed'][:4])})")
    for c in d["parts_changed"][:4]:
        k, (old, new) = next((k, v) for k, v in c["changes"].items() if k != "placement") \
            if any(k != "placement" for k in c["changes"]) else ("placement", (None, None))
        bits.append(f"{c['ref']} moved" if k == "placement" else f"{c['ref']} {k} {old or '–'} → {new or '–'}")
    if len(d["parts_changed"]) > 4:
        bits.append(f"{len(d['parts_changed']) - 4} more parts changed")
    nn = len(d["nets_added"]) + len(d["nets_removed"]) + len(d["nets_changed"])
    if nn:
        bits.append(f"{nn} net{'s' if nn != 1 else ''} changed")
    for k, (old, new) in list(d["board"].items())[:3]:
        if not isinstance(old, (dict, list)) and not isinstance(new, (dict, list)):
            bits.append(f"board {k.replace('_mm', '').replace('_', ' ')} {old} → {new}")
        else:
            bits.append(f"board {k.replace('_', ' ')} changed")
    if d["rules"]:
        bits.append("design rules changed")
    for section,label in (('fixed_copper','PCB copper changed'),('fixed_zones','copper zones changed'),('library','project library changed'),('editor','schematic drawing changed')):
        if section in d.get('changed_sections',[]):bits.append(label)
    if not bits and d.get('field_change_count'):bits.append('project metadata changed')
    return ", ".join(bits) or "no design changes (rebuilt)"


def _part(c: dict) -> dict:
    return {k: c.get(k) for k in ("ref", "value", "footprint", "lcsc")}


def _ref_key(ref: str):
    m = re.match(r"([A-Za-z_]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def load(p: Project, rev: int) -> dict:
    spec = _spec(p.root / f"rev{int(rev)}")
    if spec is None:
        raise KeyError(f"revision {rev} not found")
    return spec
