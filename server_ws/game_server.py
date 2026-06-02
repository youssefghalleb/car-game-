import asyncio
import json
import os
import time
import uuid

from aiohttp import web, WSMsgType

from server_ws.room import Room
from server_ws import shared_pairing


# ============================================================
# Serveur WebSocket multijoueur
# ============================================================
# Point d'entrée du backend Python.
# Gère :
# - connexion/déconnexion des joueurs
# - dispatch des messages WebSocket
# - boucle de jeu (tick) à 60 Hz
# - broadcast de l'état à ~24 Hz
# ============================================================

TICK_RATE = 60          # Simulation ticks per second
BROADCAST_RATE = 24     # State broadcasts per second
LOBBY_REFRESH_RATE = 4  # Pairing/status refreshes per second
WS_HEARTBEAT_SECONDS = 20.0
WS_REPLACED_CLOSE_CODE = 4001
STATE_SEND_TIMEOUT_SECONDS = 1.0
DEBUG_CONTROLLER = os.environ.get("DEBUG_CONTROLLER", "0") == "1"

# Active rooms
rooms: dict[str, Room] = {}
room_tasks: dict[str, asyncio.Task] = {}


def log_controller(message: str):
    if DEBUG_CONTROLLER:
        print(f"[ControllerTrace] {message}", flush=True)


def normalize_room_id(room_id: str | None) -> str:
    raw = str(room_id or "default")
    cleaned = "".join(ch for ch in raw.upper() if ch.isalnum() or ch in ("-", "_"))
    return cleaned[:32] or "DEFAULT"


def get_or_create_room(room_id: str) -> Room:
    if room_id not in rooms:
        log_controller(f"room_create room={room_id}")
        rooms[room_id] = Room(room_id)
    return rooms[room_id]


def ensure_room_loop(room: Room):
    task = room_tasks.get(room.room_id)
    if task is None or task.done():
        room_tasks[room.room_id] = asyncio.create_task(room_loop(room))


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle a player WebSocket connection."""
    raw_room_id = request.match_info.get("room_id", "default")
    room_id = normalize_room_id(raw_room_id)
    connection_id = uuid.uuid4().hex[:8]
    ws = web.WebSocketResponse(
        heartbeat=WS_HEARTBEAT_SECONDS,
        autoping=True,
    )
    await ws.prepare(request)
    log_controller(f"ws_open connection={connection_id} raw_room={raw_room_id} room={room_id} path={request.path}")

    room = get_or_create_room(room_id)
    player_id = None
    role = None
    remote_controller = False
    spectator_id = None

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    action = data.get("action")

                    if action == "join":
                        name = data.get("name", "Player")[:20]
                        role = data.get("role", "display")
                        requested_player_id = data.get("player_id")
                        log_controller(
                            f"join_request connection={connection_id} room={room_id} "
                            f"role={role} requested_player={requested_player_id}"
                        )

                        if role == "controller":
                            player_id = room._sanitize_player_id(requested_player_id) or ""
                            attached, old_ws = room.attach_controller(player_id, ws)
                            if not attached:
                                if shared_pairing.player_exists(room_id, player_id):
                                    remote_controller = True
                                    shared_pairing.mark_controller(room_id, player_id)
                                    old_ws = None
                                    log_controller(
                                        f"controller_pair_remote_success connection={connection_id} "
                                        f"room={room_id} player={player_id}"
                                    )
                                else:
                                    log_controller(
                                        f"controller_pair_fail connection={connection_id} room={room_id} "
                                        f"player={player_id} existing_players={list(room.players.keys())}"
                                    )
                                    await ws.send_json({"error": "player_not_found"})
                                    await ws.close()
                                    return ws
                            if old_ws is not None and old_ws is not ws and not old_ws.closed:
                                await old_ws.close(code=WS_REPLACED_CLOSE_CODE, message=b"replaced")
                            log_controller(
                                f"controller_pair_success connection={connection_id} room={room_id} "
                                f"player={player_id} replaced={old_ws is not None}"
                            )
                            await ws.send_json({
                                "action": "joined",
                                "role": "controller",
                                "connection_id": connection_id,
                                "player_id": player_id,
                                "room_id": room_id,
                            })
                            await broadcast_state(room)
                            continue

                        if role == "spectator":
                            role = "spectator"
                            spectator_id = room.add_spectator(name, ws)
                            ensure_room_loop(room)
                            await ws.send_json({
                                "action": "joined",
                                "role": "spectator",
                                "connection_id": connection_id,
                                "spectator_id": spectator_id,
                                "room_id": room_id,
                            })
                            await ws.send_str(json.dumps(
                                room.get_state_snapshot(
                                    include_track=room.race is not None,
                                    include_meta=True,
                                ),
                                separators=(",", ":"),
                            ))
                            await broadcast_state(room)
                            continue

                        role = "display"
                        player_id, old_ws = room.add_display(name, ws, requested_player_id)
                        if player_id is None:
                            log_controller(
                                f"display_register_fail connection={connection_id} room={room_id} "
                                f"requested_player={requested_player_id} state={room.state} players={room.player_count}"
                            )
                            await ws.send_json({"error": "room_full"})
                            await ws.close()
                            return ws
                        if old_ws is not None and old_ws is not ws and not old_ws.closed:
                            await old_ws.close(code=WS_REPLACED_CLOSE_CODE, message=b"replaced")
                        log_controller(
                            f"display_register_success connection={connection_id} room={room_id} "
                            f"player={player_id} replaced={old_ws is not None}"
                        )
                        ensure_room_loop(room)
                        await ws.send_json({
                            "action": "joined",
                            "role": "display",
                            "connection_id": connection_id,
                            "player_id": player_id,
                            "room_id": room_id,
                        })
                        await broadcast_state(room)

                    elif action == "input" and player_id:
                        if role == "controller":
                            shared_pairing.write_input(room_id, player_id, data)
                        updated = False if remote_controller else room.update_input(player_id, data)
                        if not updated and not remote_controller:
                            log_controller(
                                f"input_drop connection={connection_id} room={room_id} "
                                f"role={role} player={player_id}"
                            )

                    elif action == "start" and player_id and role == "display":
                        if not room.is_host(player_id):
                            await ws.send_json({"error": "host_only"})
                            continue
                        started, blockers = room.start_race()
                        if not started:
                            await ws.send_json({
                                "error": "not_ready",
                                "blockers": blockers,
                            })
                        await broadcast_state(room, include_track=started)

                    elif action == "settings" and player_id and role == "display":
                        if room.state == "lobby" and room.is_host(player_id):
                            for key in ("laps_to_win", "bot_count", "bot_difficulty",
                                        "car_damage", "track_layout", "steer_assist",
                                        "race_mode"):
                                if key in data:
                                    room.settings[key] = data[key]
                            await broadcast_state(room)
                        elif room.state == "lobby":
                            await ws.send_json({"error": "host_only"})

                    elif action == "ready" and player_id:
                        ready = bool(data.get("ready", True))
                        changed = room.set_ready(player_id, role or "display", ready)
                        log_controller(
                            f"ready_update connection={connection_id} room={room_id} "
                            f"role={role} player={player_id} ready={ready} accepted={changed}"
                        )
                        await broadcast_state(room)

                    elif action == "pause" and player_id:
                        room.pause_race()
                        await broadcast_state(room)

                    elif action == "resume" and player_id:
                        room.resume_race()
                        await broadcast_state(room)

                    elif action == "restart" and player_id:
                        room.restart_race()
                        await broadcast_state(room, include_track=True)

                    elif action == "reset" and player_id:
                        room.reset_race()
                        await broadcast_state(room, include_track=True)

                    elif action == "quit" and player_id and role == "display":
                        room.quit_to_lobby()
                        await broadcast_state(room)

                    elif action == "chat":
                        sender = "Spectator"
                        if role == "display" and player_id in room.players:
                            sender = room.players[player_id].name
                        elif role == "spectator" and spectator_id in room.spectators:
                            sender = room.spectators[spectator_id].name
                        room.add_chat_message(sender, data.get("text", ""))
                        await broadcast_state(room)

                except Exception as e:
                    log_controller(
                        f"ws_message_error connection={connection_id} room={room_id} "
                        f"role={role} player={player_id} error={e}"
                    )

            elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break

    finally:
        if player_id and role == "controller":
            detached = room.detach_controller(player_id, ws)
            if detached:
                log_controller(f"controller_close connection={connection_id} room={room_id} player={player_id}")
            if detached and room.player_count:
                await broadcast_state(room)
        elif player_id and role == "display":
            detached = room.detach_display(player_id, ws)
            if detached:
                log_controller(f"display_close connection={connection_id} room={room_id} player={player_id}")
                await broadcast_state(room)
            room.cleanup_inactive_players(grace_seconds=30.0)
            shared_pairing.cleanup()
            if room.active_count == 0:
                log_controller(f"room_remove_empty room={room_id}")
                rooms.pop(room_id, None)
        elif spectator_id and role == "spectator":
            detached = room.detach_spectator(spectator_id, ws)
            if detached:
                log_controller(f"spectator_close connection={connection_id} room={room_id} spectator={spectator_id}")
                await broadcast_state(room)
            if room.active_count == 0:
                log_controller(f"room_remove_empty room={room_id}")
                rooms.pop(room_id, None)

    log_controller(f"ws_close connection={connection_id} room={room_id} role={role} player={player_id}")

    return ws


async def room_loop(room: Room):
    tick_interval = 1.0 / TICK_RATE
    broadcast_interval = 1.0 / BROADCAST_RATE
    lobby_interval = 1.0 / LOBBY_REFRESH_RATE
    last_tick = time.perf_counter()
    last_broadcast = 0.0

    try:
        while room.active_count > 0:
            now = time.perf_counter()
            dt = min(now - last_tick, tick_interval * 2)
            last_tick = now

            room.cleanup_inactive_players(grace_seconds=30.0)
            if room.state in ("countdown", "racing"):
                room.tick(dt)

            interval = lobby_interval if room.state == "lobby" else broadcast_interval
            if now - last_broadcast >= interval:
                last_broadcast = now
                await broadcast_state(room, include_meta=room.state == "lobby")

            await asyncio.sleep(tick_interval)
    finally:
        room_tasks.pop(room.room_id, None)


async def broadcast_state(room: Room, include_track: bool = False, include_meta: bool = True):
    """Send current state to all players in a room."""
    snapshot = room.get_state_snapshot(include_track=include_track, include_meta=include_meta)
    msg = json.dumps(snapshot, separators=(",", ":"))

    recipients = [
        (pid, slot, slot.display_ws, False)
        for pid, slot in room.players.items()
    ] + [
        (sid, slot, slot.ws, True)
        for sid, slot in room.spectators.items()
    ]

    for pid, slot, ws, is_spectator in recipients:
        if ws is None or ws.closed:
            continue

        task = slot._display_send_task
        if task is not None and task.done():
            slot._display_send_task = None
            task = None

        if task is not None:
            slot._dropped_state_frames += 1
            now = time.monotonic()
            if now - slot._last_send_drop_log >= 2.0:
                slot._last_send_drop_log = now
                log_controller(
                    f"state_frame_skip room={room.room_id} player={pid} "
                    f"dropped={slot._dropped_state_frames}"
                )
            if include_track:
                task.cancel()
                slot._display_send_task = None
            else:
                continue

        slot._display_send_task = asyncio.create_task(
            send_display_state(room, pid, slot, ws, msg)
        )

        if is_spectator:
            continue

        controller_ws = slot.controller_ws
        if controller_ws is None or controller_ws.closed:
            continue

        controller_task = slot._controller_send_task
        if controller_task is not None and controller_task.done():
            slot._controller_send_task = None
            controller_task = None
        if controller_task is not None:
            continue

        telemetry = build_controller_telemetry(snapshot, pid)
        if telemetry is not None:
            slot._controller_send_task = asyncio.create_task(
                send_controller_state(room, pid, slot, controller_ws, telemetry)
            )


async def send_display_state(room: Room, player_id: str, slot, ws: web.WebSocketResponse, msg: str):
    try:
        await asyncio.wait_for(ws.send_str(msg), timeout=STATE_SEND_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        current_ws = getattr(slot, "display_ws", getattr(slot, "ws", None))
        if current_ws is ws:
            log_controller(
                f"display_send_fail room={room.room_id} player={player_id} "
                f"error={type(exc).__name__}"
            )
            if str(player_id).startswith("S"):
                room.detach_spectator(player_id, ws)
            else:
                room.detach_display(player_id, ws)
    finally:
        if slot._display_send_task is asyncio.current_task():
            slot._display_send_task = None


def build_controller_telemetry(snapshot: dict, player_id: str) -> dict | None:
    telemetry = {
        "type": "telemetry",
        "state": snapshot.get("state"),
    }
    if "countdown" in snapshot:
        telemetry["countdown"] = snapshot["countdown"]

    car = None
    for candidate in snapshot.get("cars", []) or []:
        if candidate.get("id") == player_id:
            car = candidate
            break
    if car:
        telemetry["speed"] = car.get("speed", 0)
        telemetry["nitro_amount"] = car.get("nitro_amount", 0)
        telemetry["health"] = car.get("health", 0)
        telemetry["wrong_way"] = car.get("wrong_way", False)
        telemetry["shortcut_warning"] = car.get("shortcut_warning", False)
        telemetry["invalid_lap_warning"] = car.get("invalid_lap_warning", False)
        telemetry["off_track_warning"] = car.get("off_track_warning", False)

    if snapshot.get("crash_events"):
        telemetry["collision"] = True
    if snapshot.get("leaderboard"):
        telemetry["finished"] = True

    return telemetry


async def send_controller_state(room: Room, player_id: str, slot, ws: web.WebSocketResponse, payload: dict):
    try:
        msg = json.dumps(payload, separators=(",", ":"))
        await asyncio.wait_for(ws.send_str(msg), timeout=STATE_SEND_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception:
        if slot.controller_ws is ws:
            room.detach_controller(player_id, ws)
    finally:
        if slot._controller_send_task is asyncio.current_task():
            slot._controller_send_task = None


async def game_loop(app: web.Application):
    """Cleanup loop for active rooms. Per-room tasks own ticking/broadcasts."""
    cleanup_interval = 1.0

    while True:
        shared_pairing.cleanup()
        for room in list(rooms.values()):
            room.cleanup_inactive_players(grace_seconds=30.0)
            if room.active_count == 0:
                rooms.pop(room.room_id, None)
                task = room_tasks.pop(room.room_id, None)
                if task is not None:
                    task.cancel()
        await asyncio.sleep(cleanup_interval)


async def start_background_tasks(app: web.Application):
    app["game_loop"] = asyncio.create_task(game_loop(app))


async def cleanup_background_tasks(app: web.Application):
    app["game_loop"].cancel()
    try:
        await app["game_loop"]
    except asyncio.CancelledError:
        pass


async def health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def room_list(request: web.Request) -> web.Response:
    """List active rooms."""
    result = []
    for rid, room in rooms.items():
        result.append({
            "room_id": rid,
            "state": room.state,
            "players": room.player_count,
            "spectators": len(room.spectators),
        })
    return web.json_response(result)


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/api/rooms", room_list)
    app.router.add_get("/ws/{room_id}", websocket_handler)
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    return app


def run_server(host="0.0.0.0", port=8765):
    """Start the game server."""
    app = create_app()
    print(f"Game server starting on http://{host}:{port}")
    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
