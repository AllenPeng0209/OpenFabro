"""Validate display-only object organization, independent of native geometry availability.

Absent/deleted object identities may remain as historical membership. The frontend only
applies membership when the object's current natural category agrees with the group.
"""
from __future__ import annotations

import re


def rename_net(spec: dict, old: str, new: str) -> None:
    """Rebase logical membership/category keys; preserve a merge destination's membership."""
    replace = lambda value: 'net:' + new if value == 'net:' + old else value
    for state in ((spec.get('editor') or {}).get('object_tree') or {}).values():
        for group in state.get('groups', {}).values():
            group['parent'] = replace(group['parent'])
        entries = list(state.get('parents', {}).items())
        state['parents'] = {replace(key): parent for key, parent in sorted(entries, key=lambda item: replace(item[0]) == item[0])}
        order = {}
        for parent, ids in sorted(state.get('order', {}).items(), key=lambda item: replace(item[0]) != item[0]):
            key = replace(parent)
            order[key] = list(dict.fromkeys([*order.get(key, []), *(replace(item) for item in ids)]))
        state['order'] = order


def _group(value):
    return isinstance(value, str) and re.fullmatch(r'user-group:[A-Za-z0-9_-]{1,80}', value) is not None


def _item(value):
    return isinstance(value, str) and len(value.encode('utf-16-le')) // 2 <= 256 and re.fullmatch(
        r'(?:component|symbol|net|pad|track|arc|via|zone|drawing|outline|wire|node):.+', value) is not None


def _category(value):
    return isinstance(value, str) and len(value.encode('utf-16-le')) // 2 <= 256 and re.fullmatch(
        r'(?:components|nets|zones|graphics|outline)|(?:components|wires|nodes|labels):.*|(?:component|net|pads|graphics):.+', value) is not None


def validate(spec: dict) -> None:
    value = (spec.get('editor') or {}).get('object_tree')
    if value is None:
        return
    if not isinstance(value, dict) or set(value) - {'layout', 'schematic'}:
        raise ValueError('Object groups need layout or schematic metadata.')
    for state in value.values():
        if not isinstance(state, dict) or set(state) - {'groups', 'parents', 'order'}:
            raise ValueError('Object group metadata must contain groups, parents and order.')
        groups, parents, order = (state.get(key) if state.get(key) is not None else {} for key in ('groups', 'parents', 'order'))
        if any(not isinstance(item, dict) for item in (groups, parents, order)) or len(groups) > 1000 or len(parents) > 20000 or len(order) > 20000:
            raise ValueError('Object group metadata is too large or malformed.')
        for key, group in groups.items():
            if not _group(key) or not isinstance(group, dict) or set(group) - {'name', 'parent'}:
                raise ValueError('Each object group needs a valid identity, name and parent category.')
            name, parent = group.get('name'), group.get('parent')
            if not isinstance(name, str) or not name.strip() or len(name.encode('utf-16-le')) // 2 > 120 or not (_category(parent) or _group(parent)):
                raise ValueError('Each object group needs a valid identity, name and parent category.')
        for key, group in groups.items():
            seen, parent = {key}, group['parent']
            while _group(parent):
                if parent in seen:
                    raise ValueError('Object groups cannot contain a parent cycle.')
                seen.add(parent)
                if parent not in groups:
                    raise ValueError('An object group parent does not exist.')
                parent = groups[parent]['parent']
        for key, parent in parents.items():
            if not _item(key) or not _group(parent) or parent not in groups:
                raise ValueError('Group members must refer to an existing object group.')
        for parent, ids in order.items():
            if not (_category(parent) or _group(parent) and parent in groups) or not isinstance(ids, list) or len(ids) > 20000:
                raise ValueError('Object order must contain distinct object identities within a category.')
            seen = set()
            for key in ids:
                if not (_item(key) or _group(key) and key in groups) or key in seen:
                    raise ValueError('Object order must contain distinct object identities within a category.')
                seen.add(key)
