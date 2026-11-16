"""Reserved project paths, including aliases on case-insensitive filesystems."""
from pathlib import Path


def protected_output(root, target, reserved):
    root, target = Path(root).resolve(), Path(target).resolve()
    if not target.is_relative_to(root):
        return True
    rel = target.relative_to(root)
    if not rel.parts or rel.as_posix() in reserved or rel.parts[0] in {"native", "history", "mechanical"} or rel.parts[:2]==('references','canvas'):
        return True
    # Do not casefold every path: Linux can have a distinct user folder named Native.
    for name in ("native", "history", "mechanical", "references/canvas"):
        boundary = root / name
        if not boundary.is_dir():
            continue
        for parent in target.parents:
            if parent == root:
                break
            try:
                if parent.samefile(boundary):
                    return True
            except OSError:
                continue
    for name in reserved:
        try:
            if target.samefile(root / name):
                return True
        except OSError:
            continue
    return False
