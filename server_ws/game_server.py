import asyncio
import json
import time
import uuid

from aiohttp import web, WSMsgType

from server_ws.room import Room


# ============================================================
# Serveur WebSocket multijoueur
# ============================================================
# Point d'entrée du backend Python.
# Gère :
# - connexion/déconnexion des joueurs
# - dispatch des messages WebSocket
# - boucle de jeu (tick) à 60 Hz
# - broadcast de l'état à ~20 Hz
# ============================================================

TICK_RATE = 60          # Simulation ticks per second
BROADCAST_RATE = 20     # State broadcasts per second

# Active rooms
rooms: dict[str, Room] = {}


def get_or_create_room(room_id: str) -> Room:
    if room_id not in rooms:
        rooms[room_id] = Room(room_id)
    return rooms[room_id]


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle a player WebSocket connection."""
    room_id = request.match_info.get("room_id", "default")
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    room = get_or_create_room(room_id)
    player_id = None

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    action = data.get("action")

                    if action == "join":
                        name = data.get("name", "Player")[:20]
                        player_id = room.add_player(name, ws)
                        if player_id is None:
                            await ws.send_json({"error": "room_full"})
                            await ws.close()
                            return ws
                        print(f"[Room {room_id}] Player '{name}' joined as id={player_id}")
                        await ws.send_json({
                            "action": "joined",
                            "player_id": player_id,
                            "room_id": room_id,
                        })
                        await broadcast_state(room)

                    elif action == "input" and player_id:
                        room.update_input(player_id, data)

                    elif action == "start" and player_id:
                        print(f"[Room {room_id}] Start requested by player {player_id}, room state: {room.state}")
                        room.start_race()
                        print(f"[Room {room_id}] Race started, new state: {room.state}")
                        await broadcast_state(room)

                    elif action == "settings" and player_id:
                        if room.state == "lobby":
                            for key in ("laps_to_win", "bot_count", "bot_difficulty",
                                        "car_damage", "track_layout"):
                                if key in data:
                                    room.settings[key] = data[key]
                            print(f"[Room {room_id}] Settings updated: {room.settings}")
                            await broadcast_state(room)

                except Exception as e:
                    print(f"WS error: {e}")

            elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break

    finally:
        if player_id:
            room.remove_player(player_id)
            if room.player_count == 0:
                rooms.pop(room_id, None)
            else:
                await broadcast_state(room)

    return ws


async def broadcast_state(room: Room):
    """Send current state to all players in a room."""
    snapshot = room.get_state_snapshot()
    msg = json.dumps(snapshot)
    disconnected = []

    for pid, slot in room.players.items():
        try:
            await slot.ws.send_str(msg)
        except Exception:
            disconnected.append(pid)

    for pid in disconnected:
        room.remove_player(pid)


async def game_loop(app: web.Application):
    """Main game loop running all active rooms."""
    tick_interval = 1.0 / TICK_RATE
    broadcast_interval = 1.0 / BROADCAST_RATE
    last_broadcast = 0.0

    while True:
        t0 = time.perf_counter()

        for room in list(rooms.values()):
            if room.state in ("countdown", "racing"):
                room.tick(tick_interval)

        now = time.perf_counter()
        if now - last_broadcast >= broadcast_interval:
            last_broadcast = now
            for room in list(rooms.values()):
                if room.state != "lobby":
                    await broadcast_state(room)

        elapsed = time.perf_counter() - t0
        sleep_time = max(0, tick_interval - elapsed)
        await asyncio.sleep(sleep_time)


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
