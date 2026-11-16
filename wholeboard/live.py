"""Ephemeral collaboration presence alongside the durable project event stream."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
import uuid

import anyio
from fastapi import WebSocketDisconnect

from . import collaboration

VIEWS = {"schematic", "layout", "3d", "files", "bom", "components", "nets", "blocks", "review", "simulation", "pins", "rules", "knowledge"}
COLORS = ("#85c9fb", "#f0b978", "#dd92d9", "#b6cd6b", "#a0b4ff", "#78d4b4")


def _broadcast(p):
    with p.lock:
        message = {"type": "presence", "users": [dict(user) for user in p.presence.values()]}
        listeners = list(p.presence_listeners)
    for fn in listeners:
        try:
            fn(message)
        except RuntimeError:
            pass


def _update(p, client_id: str, message: dict):
    view = message.get("view")
    if view not in VIEWS:
        return
    sheet = message.get("sheet", "")
    if not isinstance(sheet, str) or len(sheet) > 100:
        return
    ref = message.get("ref")
    if ref not in {c["ref"] for c in (p.state.get("spec") or {}).get("components", [])}:
        ref = None
    cursor = message.get("cursor")
    if view not in ("schematic", "layout") or not isinstance(cursor, list) or len(cursor) != 2 or any(not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 1_000_000 for v in cursor):
        cursor = None
    with p.lock:
        if client_id in p.presence:
            p.presence[client_id].update(view=view, sheet=sheet, ref=ref, cursor=cursor)
    _broadcast(p)


async def connect(websocket, p, after=0):
    await websocket.accept()
    loop, queue = asyncio.get_running_loop(), asyncio.Queue()
    client_id, actor = uuid.uuid4().hex[:16], collaboration.identity(websocket.scope)
    color = COLORS[int(hashlib.sha256(actor["id"].encode()).hexdigest()[:4], 16) % len(COLORS)]

    def listener(event):
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def allowed():
        return bool(collaboration.project_role(collaboration.identity(websocket.scope, refresh=True), p))

    with p.lock:
        backlog = [e for e in p.events if e["seq"] > after]
        p.listeners.append(listener)
        p.presence_listeners.append(listener)
        p.presence[client_id] = {"id": client_id, "name": actor["name"], "color": color, "view": "schematic", "sheet": "", "ref": None, "cursor": None}
    _broadcast(p)
    incoming = outgoing = None
    try:
        for event in backlog:
            if not allowed():
                await websocket.close(code=4403)
                return
            await websocket.send_text(json.dumps(event))
        incoming, outgoing = asyncio.create_task(websocket.receive()), asyncio.create_task(queue.get())
        last_update = 0
        while True:
            done, _ = await asyncio.wait((incoming, outgoing), timeout=.5, return_when=asyncio.FIRST_COMPLETED)
            if not allowed():
                await websocket.close(code=4403)
                return
            if incoming in done:
                packet = incoming.result()
                if packet["type"] == "websocket.disconnect":
                    return
                raw = packet.get("text") or ""
                if len(raw) > 8192:
                    await websocket.close(code=1009)
                    return
                if raw and time.monotonic() - last_update >= .045:
                    try:
                        message = json.loads(raw)
                        if isinstance(message, dict) and message.get("type") == "presence":
                            _update(p, client_id, message)
                            last_update = time.monotonic()
                    except (ValueError, TypeError):
                        pass
                incoming = asyncio.create_task(websocket.receive())
            if outgoing in done:
                event = outgoing.result()
                if event.get("type") == "presence":
                    event = {**event, "self": client_id}
                await websocket.send_text(json.dumps(event))
                outgoing = asyncio.create_task(queue.get())
    except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
        pass
    finally:
        pending = [task for task in (incoming, outgoing) if task]
        for task in pending:
            task.cancel()
        if pending:
            with anyio.CancelScope(shield=True):
                await asyncio.gather(*pending, return_exceptions=True)
        with p.lock:
            for listeners in (p.listeners, p.presence_listeners):
                if listener in listeners:
                    listeners.remove(listener)
            p.presence.pop(client_id, None)
        _broadcast(p)
