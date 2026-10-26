"""
core/conference_server.py — Local HTTP & WebSocket server for the 3D Video Conference UI.

Serves the 3D WebGL avatar interface, handles real-time viseme and state broadcasting,
and connects conference controls (Mute, Interrupt, Chat, Settings) to the Jarvis backend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
AVATAR_DIR = BASE_DIR / "avatar"
PORT = int(os.environ.get("PORT", "8085"))
HOST = os.environ.get("HOST", "0.0.0.0")


class ConferenceServer:
    def __init__(self, port: int = PORT, host: str = HOST):
        self.port = int(os.environ.get("PORT", port))
        self.host = host
        self.app = FastAPI(title="ZainAI Conference Server")
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.active_websockets: list[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

        # Callbacks hooked by JarvisUI
        self.on_interrupt: Callable[[], None] | None = None
        self.on_mute_toggled: Callable[[bool], None] | None = None
        self.on_text_command: Callable[[str], None] | None = None
        self.on_voice_changed: Callable[[str], None] | None = None
        self.on_screen_capture: Callable[[], None] | None = None
        self.on_leave_call: Callable[[], None] | None = None
        self.on_start_call: Callable[[], None] | None = None

        self._setup_routes()

    def _setup_routes(self) -> None:
        @self.app.get("/")
        async def index():
            index_file = WEB_DIR / "index.html"
            if index_file.exists():
                return FileResponse(
                    index_file,
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
                )
            return HTMLResponse("<h1>Conference interface not found</h1>", status_code=404)

        @self.app.get("/avatar/lipsync_eyes.glb")
        @self.app.get("/avatar/ZainAI.glb")
        async def get_avatar():
            glb_file = AVATAR_DIR / "lipsync_eyes.glb"
            if not glb_file.exists():
                glb_file = AVATAR_DIR / "ZainAI.glb"
            if glb_file.exists():
                return FileResponse(
                    glb_file,
                    media_type="model/gltf-binary",
                    filename=glb_file.name
                )
            return HTMLResponse("Avatar file not found", status_code=404)

        if WEB_DIR.exists():
            self.app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")

        @self.app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            await ws.accept()
            self.active_websockets.append(ws)
            try:
                while True:
                    text = await ws.receive_text()
                    try:
                        data = json.loads(text)
                        action = data.get("action")
                        if action == "interrupt" and self.on_interrupt:
                            self.on_interrupt()
                        elif action == "toggle_mute" and self.on_mute_toggled:
                            self.on_mute_toggled(bool(data.get("muted", False)))
                        elif action == "command" and self.on_text_command:
                            cmd = data.get("text", "").strip()
                            if cmd:
                                self.on_text_command(cmd)
                        elif action == "voice_changed" and self.on_voice_changed:
                            self.on_voice_changed(data.get("voice", ""))
                        elif action == "screen_capture" and self.on_screen_capture:
                            self.on_screen_capture()
                        elif action == "leave" and self.on_leave_call:
                            self.on_leave_call()
                        elif action in ("start_call", "wake") and self.on_start_call:
                            self.on_start_call()
                    except Exception as e:
                        print(f"[ConferenceServer] WS message error: {e}")
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass
            finally:
                if ws in self.active_websockets:
                    self.active_websockets.remove(ws)

    def start(self) -> None:
        """Start the conference HTTP + WS server in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            return

        def _run():
            config = uvicorn.Config(
                self.app,
                host=self.host,
                port=self.port,
                log_level="warning",
                access_log=False
            )
            self._server = uvicorn.Server(config)
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._server.serve())

        self._thread = threading.Thread(target=_run, daemon=True, name="ConferenceServer")
        self._thread.start()
        print(f"[ConferenceServer] Running on http://{self.host}:{self.port}")

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True

    def broadcast(self, message: dict[str, Any]) -> None:
        """Thread-safe broadcast to all connected WebSocket clients."""
        if not self.active_websockets or not self._loop or not self._loop.is_running():
            return

        text = json.dumps(message)

        async def _send():
            dead = []
            for ws in self.active_websockets:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in self.active_websockets:
                    self.active_websockets.remove(ws)

        try:
            asyncio.run_coroutine_threadsafe(_send(), self._loop)
        except Exception:
            pass

    def broadcast_state(self, state: str) -> None:
        self.broadcast({"type": "state", "state": state})

    def broadcast_audio_level(self, level: float) -> None:
        self.broadcast({"type": "audio_level", "level": round(float(level), 3)})

    def broadcast_viseme(self, level: float, openness: float, width: float, tag: str = "") -> None:
        self.broadcast({
            "type": "viseme",
            "level": round(float(level), 3),
            "openness": round(float(openness), 3),
            "width": round(float(width), 3),
            "tag": str(tag or "")
        })

    def broadcast_log(self, text: str) -> None:
        self.broadcast({"type": "log", "message": text})

    def broadcast_content(self, title: str, text: str) -> None:
        self.broadcast({"type": "content", "title": title, "text": text})

    def broadcast_mute(self, muted: bool) -> None:
        self.broadcast({"type": "mute", "muted": muted})


_instance: ConferenceServer | None = None


def get_conference_server() -> ConferenceServer:
    global _instance
    if _instance is None:
        _instance = ConferenceServer()
        _instance.start()
    return _instance
