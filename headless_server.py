"""
headless_server.py — Headless Cloud Run / Docker runner for ZainAI 3D Conference UI.

Runs the FastAPI + WebSocket conference server in the foreground, connects
browser audio/text commands to Gemini, and serves the 3D WebGL avatar interface.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import sys

import uvicorn
from core.conference_server import ConferenceServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HeadlessZainAI")

BASE_DIR = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

def get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    cfg_file = BASE_DIR / "config" / "api_keys.json"
    if cfg_file.exists():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            return data.get("gemini_api_key", "").strip()
        except Exception:
            pass
    return ""


class HeadlessSession:
    def __init__(self, server: ConferenceServer):
        self.server = server
        self.api_key = get_api_key()
        self.client = None
        self.chat = None
        self.model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self._init_gemini()
        self._wire_callbacks()

    def _init_gemini(self) -> None:
        if not self.api_key:
            logger.warning("No GEMINI_API_KEY set. Live AI answers will be limited until configured.")
            return
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            self.chat = self.client.chats.create(
                model=self.model_name,
                config={
                    "system_instruction": (
                        "You are ZainAI (Mark-LVI), a warm, encouraging teacher and critical thinking expert. "
                        "Your mission is to help students think critically and discover answers for themselves. "
                        "NEVER act as a homework machine or give direct answers to students' questions or exercises. "
                        "Instead, guide them using the Socratic method: ask probing questions, break down problems into steps, "
                        "and encourage them to reason through to the solution. "
                        "Always maintain a supportive, patient, and intellectually engaging presence. "
                        "Keep responses spoken-friendly, concise (1-3 sentences), and always end with a guiding question."
                    )
                }
            )
            logger.info("Gemini client successfully initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")

    def _wire_callbacks(self) -> None:
        self.server.on_start_call = self._on_start_call
        self.server.on_leave_call = self._on_leave_call
        self.server.on_text_command = self._on_text_command
        self.server.on_interrupt = self._on_interrupt
        self.server.on_mute_toggled = self._on_mute_toggled

    def _on_start_call(self) -> None:
        logger.info("Conference call started by client.")
        self.server.broadcast_state("LISTENING")
        self.server.broadcast_log("SYS: Call connected. Teacher ZainAI online.")

        def _delayed_greeting():
            import time
            time.sleep(0.6)
            greeting = "Hello and welcome! I am your teacher and critical thinking guide. What is your name, and what interesting problem or question should we explore together today?"
            self.server.broadcast_content("ZainAI", greeting)
            self.server.broadcast_state("SPEAKING")
            self._simulate_visemes(duration=3.5)

        import threading
        threading.Thread(target=_delayed_greeting, daemon=True).start()

    def _on_leave_call(self) -> None:
        logger.info("Conference call ended by client.")
        self.server.broadcast_state("SLEEPING")
        self.server.broadcast_log("SYS: Call ended. Assistant entered sleeping mode.")

    def _on_interrupt(self) -> None:
        logger.info("Interrupt requested.")
        self.server.broadcast_state("LISTENING")

    def _on_mute_toggled(self, muted: bool) -> None:
        logger.info(f"Mute toggled: {muted}")
        self.server.broadcast_mute(muted)

    def _on_text_command(self, text: str) -> None:
        logger.info(f"User text command: {text}")
        if not self.client or not self.chat:
            self.api_key = get_api_key()
            self._init_gemini()

        if not self.client:
            self.server.broadcast_content("System", "GEMINI_API_KEY not configured. Please supply an API key.")
            return

        def _generate():
            try:
                self.server.broadcast_state("THINKING")
                response = self.chat.send_message(text)
                reply = response.text or "I heard you loud and clear."
                self.server.broadcast_content("ZainAI", reply)
                self.server.broadcast_state("SPEAKING")
                self._simulate_visemes(duration=min(5.0, max(1.5, len(reply.split()) * 0.28)))
            except Exception as e:
                logger.error(f"Error querying Gemini: {e}")
                self.server.broadcast_content("Error", f"Could not generate response: {e}")
                self.server.broadcast_state("LISTENING")

        import threading
        threading.Thread(target=_generate, daemon=True).start()

    def _simulate_visemes(self, duration: float) -> None:
        """Stream conversational viseme pulses to animate the 3D mouth while speaking."""
        import random
        import time

        def _stream():
            vowels = ["AA", "E", "I", "O", "U"]
            end_time = time.time() + duration
            while time.time() < end_time:
                lvl = random.uniform(0.35, 0.95)
                op = random.uniform(0.4, 0.9)
                wd = random.uniform(0.2, 0.7)
                tag = random.choice(vowels)
                self.server.broadcast_viseme(lvl, op, wd, tag)
                time.sleep(0.065)
            self.server.broadcast_viseme(0.0, 0.0, 0.0, "")
            self.server.broadcast_state("LISTENING")

        import threading
        threading.Thread(target=_stream, daemon=True).start()


def main():
    logger.info(f"Starting ZainAI Headless Conference Server on {HOST}:{PORT}")
    server = ConferenceServer(port=PORT, host=HOST)
    _session = HeadlessSession(server)

    # Run uvicorn in the main thread (blocking) for Docker / Cloud Run
    uvicorn.run(
        server.app,
        host=HOST,
        port=PORT,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
