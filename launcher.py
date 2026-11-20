#!/usr/bin/env python3
"""
DiscordMusicBot Supervisor Launcher.
Supervises main.py, manages IPC, communicates with Web UI panel over WebSocket.
"""

import os
import sys
import re
import time
import json
import uuid
import signal
import socket
import shutil
import asyncio
import hashlib
import hmac
import secrets
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Set, List

import aiohttp

# Ensure bot modules can be imported
BOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BOT_DIR))

try:
    from bot import __version__
except Exception:
    __version__ = "1.0.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [launcher] %(message)s"
)
logger = logging.getLogger("launcher")

DISCORD_TOKEN_REGEX = re.compile(r'[\w-]{24,28}\.[\w-]{6}\.[\w-]{27,40}')
PLAYLIST_NAME_REGEX = re.compile(r'^[\w\- ().]{1,64}$')

SETTING_WHITELIST = {
    'DISCORD_COMMAND_CHANNEL_ID',
    'COMMAND_PREFIX',
    'DEFAULT_VOLUME',
    'LOOP_MODE',
    'MAX_QUEUE_SIZE',
    'AUTO_LEAVE',
    'AUTO_LEAVE_DELAY',
    'IDLE_STATUS',
    'PLAYING_STATUS',
    'DJ_ROLE_NAME',
    'LOG_LEVEL',
    'MAX_HISTORY_SIZE',
    'SUPPORTED_FORMATS',
    'PLAYLISTS_DIRECTORY',
    'DATA_DIRECTORY',
    'YOUTUBE_AUTH_MODE',
    'PANEL_OWNER_IDS',
    'LOG_TO_FILE',
    'LOG_TO_CONSOLE',
    'LOG_COMMANDS',
    'LOG_DISCORD_INTERNALS',
    'LOG_YTDLP_VERBOSE',
    'LOG_AUDIO_BUFFER',
    'LOG_ROTATION_MB',
    'LOG_BACKUP_COUNT'
}

IMPORTANT_COOKIE_NAMES = {
    '__Secure-3PSID',
    '__Secure-1PSID',
    'SAPISID',
    'SID',
    'LOGIN_INFO'
}


def clean_ansi(text: str) -> str:
    """Strip ANSI escape codes from string."""
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', str(text))


def find_free_port() -> int:
    """Find a random free TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class BotLauncher:
    """Supervises main.py process and bridges Web UI over WebSocket."""

    def __init__(self, config_file: str = "config.txt", autostart: bool = True):
        self.config_path = (BOT_DIR / config_file).resolve()
        self.autostart = autostart
        self.state = "stopped"  # stopped | starting | running | stopping | crashed
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.ipc_port: Optional[int] = None
        self.ipc_token: Optional[str] = None
        self.started_at: Optional[float] = None
        self.restart_count: int = 0
        self._spawn_count: int = 0
        self._is_restarting: bool = False
        self.last_exit: Optional[Dict[str, Any]] = None
        self._recent_crashes: List[float] = []

        self.panel_enabled = False
        self.panel_url = ""
        self.panel_secret = ""
        self.panel_owner_ids: Set[str] = set()
        self.cached_owner_ids: Set[str] = set()

        self.playlists_dir = (BOT_DIR / "playlists").resolve()
        self.data_dir = (BOT_DIR / "data").resolve()
        self.log_file = (BOT_DIR / "logs/bot.log").resolve()
        self.supported_formats: Set[str] = {'.mp3', '.flac', '.ogg', '.wav'}
        self.max_upload_mb = 100

        self.panel_state_file = self.data_dir / "panel_state.json"

        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._stopping_launcher = False
        self._manual_stop = False
        self._events_relay_task: Optional[asyncio.Task] = None
        self._active_uploads: Dict[str, Dict[str, Any]] = {}

        self.load_settings()
        self.load_cached_state()

    def load_settings(self):
        """Reads config.txt and environment overrides."""
        config_dict: Dict[str, str] = {}
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        config_dict[k.strip().upper()] = v.strip()

        # Env overrides
        for k, v in os.environ.items():
            if v:
                config_dict[k.upper()] = v.strip()

        p_enabled_val = config_dict.get('PANEL_ENABLED', 'false').lower()
        self.panel_enabled = p_enabled_val in ('true', '1', 'yes', 'on')
        self.panel_url = config_dict.get('PANEL_URL', '')
        self.panel_secret = config_dict.get('PANEL_SECRET', '')

        owner_ids_str = config_dict.get('PANEL_OWNER_IDS', '')
        self.panel_owner_ids = {s.strip() for s in owner_ids_str.split(',') if s.strip().isdigit()}

        pl_dir_str = config_dict.get('PLAYLISTS_DIRECTORY', './playlists')
        self.playlists_dir = (BOT_DIR / pl_dir_str).resolve()

        data_dir_str = config_dict.get('DATA_DIRECTORY', './data')
        self.data_dir = (BOT_DIR / data_dir_str).resolve()
        self.panel_state_file = self.data_dir / "panel_state.json"

        log_file_str = config_dict.get('LOG_FILE', './logs/bot.log')
        self.log_file = (BOT_DIR / log_file_str).resolve()

        formats_str = config_dict.get('SUPPORTED_FORMATS', '.mp3,.flac,.ogg,.wav')
        self.supported_formats = {f.strip().lower() for f in formats_str.split(',') if f.strip()}

        try:
            self.max_upload_mb = int(config_dict.get('PANEL_MAX_UPLOAD_MB', '100'))
        except ValueError:
            self.max_upload_mb = 100

        # Validate panel configuration
        if self.panel_enabled:
            is_valid_url = self.panel_url.startswith('wss://') or (
                self.panel_url.startswith('ws://') and ('localhost' in self.panel_url or '127.0.0.1' in self.panel_url)
            )
            is_valid_secret = len(self.panel_secret) >= 32

            if not is_valid_url or not is_valid_secret:
                logger.error(
                    f"Invalid panel configuration! PANEL_URL valid: {is_valid_url}, "
                    f"PANEL_SECRET length >= 32: {is_valid_secret}. Disabling panel integration."
                )
                self.panel_enabled = False

    def load_cached_state(self):
        """Loads cached owner IDs from data/panel_state.json."""
        if self.panel_state_file.exists():
            try:
                with open(self.panel_state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    ids = data.get("ownerIds", [])
                    self.cached_owner_ids = {str(x) for x in ids if str(x).isdigit()}
            except Exception as e:
                logger.warning(f"Failed to read panel_state.json: {e}")

    def save_cached_state(self):
        """Saves cached owner IDs to data/panel_state.json atomically."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp_file = self.panel_state_file.with_suffix('.tmp')
            all_owners = sorted(list(self.panel_owner_ids | self.cached_owner_ids))
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump({"ownerIds": all_owners}, f, indent=2)
            tmp_file.replace(self.panel_state_file)
        except Exception as e:
            logger.warning(f"Failed to save panel_state.json: {e}")

    def is_owner(self, user_id: str) -> bool:
        """Checks if user ID has owner permissions."""
        u_str = str(user_id)
        return (u_str in self.panel_owner_ids) or (u_str in self.cached_owner_ids)

    # -------------------------------------------------------------
    # Child Process Lifecycle
    # -------------------------------------------------------------

    async def start_child(self):
        """Starts main.py as a supervised child process."""
        if self.proc and self.proc.returncode is None:
            logger.info("Child process is already running.")
            return

        self._manual_stop = False
        self._spawn_count += 1
        if self._spawn_count > 1 and not self._is_restarting:
            self.restart_count += 1
        self.state = "starting"
        await self.broadcast_lifecycle()

        self.ipc_port = find_free_port()
        self.ipc_token = secrets.token_hex(32)

        env = dict(os.environ)
        env["MUSICBOT_IPC_PORT"] = str(self.ipc_port)
        env["MUSICBOT_IPC_TOKEN"] = self.ipc_token
        env["PYTHONUNBUFFERED"] = "1"

        cmd = [sys.executable, "main.py", "--config", str(self.config_path)]
        logger.info(f"Starting child process: {' '.join(cmd)} (IPC port {self.ipc_port})")

        try:
            self.proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(BOT_DIR),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
        except Exception as e:
            logger.error(f"Failed to spawn child process: {e}")
            self.state = "crashed"
            await self.broadcast_lifecycle()
            return

        self.started_at = time.time()
        asyncio.create_task(self._pipe_stdout(self.proc))
        asyncio.create_task(self._wait_for_ready_and_monitor(self.proc))

    async def _pipe_stdout(self, proc: asyncio.subprocess.Process):
        """Pipes child stdout to launcher's stdout line-by-line."""
        if not proc.stdout:
            return
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                sys.stdout.write(line.decode("utf-8", errors="replace"))
                sys.stdout.flush()
            except Exception:
                pass

    async def _wait_for_ready_and_monitor(self, proc: asyncio.subprocess.Process):
        """Polls child IPC until ready, then monitors exit."""
        # Wait up to 60s for IPC to become available
        ready = False
        start_wait = time.time()
        while time.time() - start_wait < 60:
            if proc.returncode is not None:
                break
            try:
                res = await self._call_ipc("me", "0", None, {})
                if res.get("ok"):
                    ready = True
                    # Update cached owner IDs
                    data = res.get("data", {})
                    if "ownerIds" in data:
                        self.cached_owner_ids.update(str(x) for x in data["ownerIds"])
                        self.save_cached_state()
                    break
            except Exception:
                pass
            await asyncio.sleep(1.0)

        if ready:
            self.state = "running"
            logger.info(f"Child bot process is ready and running (PID: {proc.pid})")
            await self.broadcast_lifecycle()
            self._start_events_relay()
        else:
            if proc.returncode is None:
                logger.warning("Child process did not respond to IPC within 60s.")

        # Wait for termination
        returncode = await proc.wait()
        exit_time = time.time()
        self.last_exit = {
            "time": exit_time,
            "code": returncode,
            "uptime": int(exit_time - self.started_at) if self.started_at else 0
        }
        logger.warning(f"Child process exited with code {returncode}")

        if self._events_relay_task:
            self._events_relay_task.cancel()
            self._events_relay_task = None

        if self._manual_stop or self._stopping_launcher:
            self.state = "stopped"
            await self.broadcast_lifecycle()
            return

        # Unexpected exit / crash
        self.restart_count += 1
        now = time.time()
        self._recent_crashes.append(now)
        # Keep crashes in last 120s
        self._recent_crashes = [t for t in self._recent_crashes if now - t <= 120]

        if len(self._recent_crashes) >= 5:
            logger.error("Child process crashed 5 times within 120 seconds. Halting auto-restart.")
            self.state = "crashed"
            await self.broadcast_lifecycle()
            return

        self.state = "starting"
        await self.broadcast_lifecycle()

        # Backoff: 2s, 5s, 10s, 30s
        idx = min(self.restart_count - 1, 3)
        delay = [2, 5, 10, 30][idx]
        logger.info(f"Auto-restarting child in {delay} seconds (attempt {self.restart_count})...")
        await asyncio.sleep(delay)
        if not self._manual_stop and not self._stopping_launcher:
            await self.start_child()

    async def stop_child(self) -> bool:
        """Stops the child process gracefully (SIGTERM, then SIGKILL)."""
        if not self.proc or self.proc.returncode is not None:
            self.state = "stopped"
            await self.broadcast_lifecycle()
            return True

        self._manual_stop = True
        self.state = "stopping"
        await self.broadcast_lifecycle()

        logger.info(f"Sending SIGTERM to child process (PID: {self.proc.pid})...")
        try:
            self.proc.terminate()
        except ProcessLookupError:
            self.state = "stopped"
            await self.broadcast_lifecycle()
            return True

        # Wait up to 15s for clean shutdown
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=15.0)
            logger.info("Child process terminated cleanly.")
        except asyncio.TimeoutError:
            logger.warning("Child process did not stop within 15s. Sending SIGKILL...")
            try:
                self.proc.kill()
                await self.proc.wait()
            except ProcessLookupError:
                pass

        self.state = "stopped"
        await self.broadcast_lifecycle()
        return True

    async def restart_child(self) -> bool:
        """Stops child if running and starts fresh."""
        self.restart_count += 1
        self._is_restarting = True
        try:
            await self.stop_child()
            await self.start_child()
        finally:
            self._is_restarting = False
        return True

    # -------------------------------------------------------------
    # IPC Client (Launcher -> Child)
    # -------------------------------------------------------------

    async def _call_ipc(self, action: str, user_id: str, guild_id: Optional[str], params: Dict[str, Any]) -> Dict[str, Any]:
        """Calls child's /rpc endpoint."""
        if not self.ipc_port or not self.ipc_token:
            return {"ok": False, "code": "BOT_OFFLINE", "error": "Bot IPC is not initialized"}

        url = f"http://127.0.0.1:{self.ipc_port}/rpc"
        headers = {
            "Authorization": f"Bearer {self.ipc_token}",
            "Content-Type": "application/json"
        }
        body = {
            "action": action,
            "userId": user_id,
            "guildId": guild_id,
            "params": params
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=55)) as resp:
                if resp.status == 401:
                    return {"ok": False, "code": "INTERNAL", "error": "IPC Authentication failure"}
                return await resp.json()

    def _start_events_relay(self):
        """Relays NDJSON /events stream from child to panel WS."""
        if self._events_relay_task:
            self._events_relay_task.cancel()
        self._events_relay_task = asyncio.create_task(self._events_relay_loop())

    async def _events_relay_loop(self):
        """Reads child's /events NDJSON stream and forwards to panel."""
        while self.state == "running" and self.ipc_port and self.ipc_token:
            url = f"http://127.0.0.1:{self.ipc_port}/events"
            headers = {"Authorization": f"Bearer {self.ipc_token}"}
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=None)) as resp:
                        if resp.status != 200:
                            await asyncio.sleep(2.0)
                            continue

                        async for line in resp.content:
                            if not line:
                                break
                            text = line.decode('utf-8').strip()
                            if not text:
                                continue
                            try:
                                evt = json.loads(text)
                                kind = evt.get("kind")
                                guild_id = evt.get("guildId")
                                data = evt.get("data")
                                await self.send_panel({
                                    "t": "evt",
                                    "kind": kind,
                                    "guildId": guild_id,
                                    "data": data
                                })
                            except Exception:
                                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"IPC events relay connection dropped: {e}")
                await asyncio.sleep(2.0)

    # -------------------------------------------------------------
    # WebSocket Panel Connection & Handshake
    # -------------------------------------------------------------

    async def run_panel_ws(self):
        """Main loop for WebSocket agent connection to Web UI."""
        if not self.panel_enabled:
            logger.info("Panel integration disabled. Running standalone supervisor.")
            return

        backoff = 1.0
        while not self._stopping_launcher:
            try:
                logger.info(f"Connecting to panel: {self.panel_url}...")
                async with aiohttp.ClientSession() as session:
                    self._session = session
                    async with session.ws_connect(
                        self.panel_url,
                        max_msg_size=2 * 1024 * 1024,
                        heartbeat=25.0
                    ) as ws:
                        self._ws = ws
                        backoff = 1.0
                        handshake_ok = await self._do_handshake(ws)
                        if not handshake_ok:
                            logger.error("Panel handshake failed. Retrying in 10s...")
                            await asyncio.sleep(10.0)
                            continue

                        logger.info("Panel handshake succeeded. Ready.")
                        await self.broadcast_lifecycle()

                        # Reconnect child event relay if child is running
                        if self.state == "running":
                            self._start_events_relay()

                        await self._panel_message_loop(ws)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Panel connection error: {e}")

            self._ws = None
            self._abort_all_uploads()

            if self._stopping_launcher:
                break

            jitter = secrets.randbelow(1000) / 1000.0
            sleep_time = min(backoff + jitter, 60.0)
            logger.info(f"Reconnecting to panel in {sleep_time:.1f}s...")
            await asyncio.sleep(sleep_time)
            backoff = min(backoff * 2.0, 60.0)

    async def _do_handshake(self, ws: aiohttp.ClientWebSocketResponse) -> bool:
        """Executes mutual HMAC challenge handshake (§3.1)."""
        agent_nonce = secrets.token_hex(16)
        hello_msg = {
            "t": "hello",
            "protocol": 1,
            "version": __version__,
            "agentNonce": agent_nonce
        }
        await ws.send_json(hello_msg)

        # Wait for challenge
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error("Handshake timeout waiting for challenge")
            return False

        if msg.type != aiohttp.WSMsgType.TEXT:
            logger.error(f"Unexpected WS message type during handshake: {msg.type}")
            return False

        data = json.loads(msg.data)
        if data.get("t") != "challenge":
            logger.error(f"Expected challenge message, got: {data}")
            return False

        server_nonce = data.get("serverNonce", "")
        server_proof = data.get("serverProof", "")

        # Verify server proof: HMAC(secret, "server:" + agentNonce)
        expected_server_proof = hmac.new(
            self.panel_secret.encode('utf-8'),
            f"server:{agent_nonce}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(server_proof, expected_server_proof):
            logger.error("Server proof verification failed! (Invalid PANEL_SECRET / AGENT_SECRET mismatch)")
            await ws.close(code=4401)
            return False

        # Send agent proof: HMAC(secret, "agent:" + serverNonce)
        agent_proof = hmac.new(
            self.panel_secret.encode('utf-8'),
            f"agent:{server_nonce}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        auth_msg = {
            "t": "auth",
            "agentProof": agent_proof
        }
        await ws.send_json(auth_msg)

        # Wait for ready
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error("Handshake timeout waiting for ready")
            return False

        if msg.type != aiohttp.WSMsgType.TEXT:
            return False

        ready_data = json.loads(msg.data)
        if ready_data.get("t") != "ready":
            logger.error(f"Expected ready message, got: {ready_data}")
            return False

        return True

    async def send_panel(self, payload: Dict[str, Any]):
        """Sends JSON frame to panel WebSocket."""
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_json(payload)
            except Exception as e:
                logger.debug(f"Failed to send to panel WS: {e}")

    async def broadcast_lifecycle(self):
        """Sends lifecycle event to panel."""
        await self.send_panel({
            "t": "evt",
            "kind": "lifecycle",
            "guildId": None,
            "data": {
                "state": self.state,
                "version": __version__
            }
        })

    async def _panel_message_loop(self, ws: aiohttp.ClientWebSocketResponse):
        """Handles incoming messages from panel WebSocket."""
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    msg_type = data.get("t")
                    if msg_type == "req":
                        asyncio.create_task(self._handle_panel_request(data))
                except Exception as e:
                    logger.error(f"Error parsing panel message: {e}")
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await self._handle_binary_frame(msg.data)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    # -------------------------------------------------------------
    # Request Routing & Launcher Actions
    # -------------------------------------------------------------

    async def _handle_panel_request(self, req: Dict[str, Any]):
        """Routes request to launcher action or forwards to child."""
        req_id = req.get("id")
        user_id = str(req.get("userId", ""))
        action = req.get("action", "")
        guild_id = req.get("guildId")
        params = req.get("params") or {}

        # 1. Launcher-handled actions
        launcher_handlers = {
            "bot.status": self._launcher_bot_status,
            "bot.start": self._launcher_bot_start,
            "bot.stop": self._launcher_bot_stop,
            "bot.restart": self._launcher_bot_restart,
            "logs.tail": self._launcher_logs_tail,
            "cookies.status": self._launcher_cookies_status,
            "cookies.get": self._launcher_cookies_get,
            "cookies.set": self._launcher_cookies_set,
            "settings.get": self._launcher_settings_get,
            "settings.set": self._launcher_settings_set,
            "playlists.create": self._launcher_playlists_create,
            "playlists.rename": self._launcher_playlists_rename,
            "playlists.delete": self._launcher_playlists_delete,
            "tracks.delete": self._launcher_tracks_delete,
            "playlists.import_youtube": self._launcher_playlists_import_youtube,
            "playlists.inspect_youtube": self._launcher_playlists_inspect_youtube,
            "upload.begin": self._launcher_upload_begin,
            "upload.end": self._launcher_upload_end,
            "upload.abort": self._launcher_upload_abort,
        }

        if action in launcher_handlers:
            # Permissions check for launcher actions (§4 table)
            # bot.status requires user in any guild or owner.
            # All other launcher actions require owner.
            if action != "bot.status" and not self.is_owner(user_id):
                await self.send_panel({
                    "t": "res",
                    "id": req_id,
                    "ok": False,
                    "code": "FORBIDDEN",
                    "error": "Owner access required"
                })
                return

            try:
                res = await launcher_handlers[action](user_id, params)
                await self.send_panel({
                    "t": "res",
                    "id": req_id,
                    **res
                })
            except Exception as e:
                clean_err = clean_ansi(str(e))
                logger.error(f"Error handling launcher action {action}: {clean_err}", exc_info=True)
                await self.send_panel({
                    "t": "res",
                    "id": req_id,
                    "ok": False,
                    "code": "INTERNAL",
                    "error": clean_err or "Internal launcher error"
                })
            return

        # 2. Bot actions: forward to child
        if self.state != "running":
            await self.send_panel({
                "t": "res",
                "id": req_id,
                "ok": False,
                "code": "BOT_OFFLINE",
                "error": f"Bot process is currently {self.state}"
            })
            return

        try:
            res = await self._call_ipc(action, user_id, guild_id, params)
            # If action was me, update cached owners
            if action == "me" and res.get("ok"):
                owners = res.get("data", {}).get("ownerIds", [])
                if owners:
                    self.cached_owner_ids.update(str(x) for x in owners)
                    self.save_cached_state()

            await self.send_panel({
                "t": "res",
                "id": req_id,
                **res
            })
        except Exception as e:
            clean_err = clean_ansi(str(e))
            logger.error(f"Error forwarding action {action} to child: {clean_err}")
            await self.send_panel({
                "t": "res",
                "id": req_id,
                "ok": False,
                "code": "INTERNAL",
                "error": clean_err
            })

    # --- Launcher Handlers ---

    async def _launcher_bot_status(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": True,
            "data": {
                "state": self.state,
                "pid": self.proc.pid if self.proc and self.proc.returncode is None else None,
                "startedAt": self.started_at,
                "restarts": self.restart_count,
                "lastExit": self.last_exit,
                "version": __version__
            }
        }

    async def _launcher_bot_start(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.state in ("running", "starting"):
            return {"ok": False, "code": "BAD_REQUEST", "error": f"Bot is already {self.state}"}
        await self.start_child()
        return {"ok": True, "data": {"state": self.state}}

    async def _launcher_bot_stop(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        await self.stop_child()
        return {"ok": True, "data": {"state": self.state}}

    async def _launcher_bot_restart(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        await self.restart_child()
        return {"ok": True, "data": {"state": self.state}}

    async def _launcher_logs_tail(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        max_lines = min(1000, max(1, int(params.get("lines", 200))))
        level_filter = params.get("level")

        if not self.log_file.exists():
            return {"ok": True, "data": {"lines": []}}

        # Read last N lines safely
        lines: List[str] = []
        try:
            with open(self.log_file, "r", encoding="utf-8", errors="replace") as f:
                # Efficient read: if file is large, seek near end
                f.seek(0, os.SEEK_END)
                size = f.tell()
                block_size = 1024 * 64
                data_buf = ""
                pos = size

                while pos > 0 and len(lines) < max_lines:
                    read_size = min(pos, block_size)
                    pos -= read_size
                    f.seek(pos)
                    chunk = f.read(read_size)
                    data_buf = chunk + data_buf
                    split_lines = data_buf.split("\n")
                    if pos > 0:
                        data_buf = split_lines[0]
                        split_lines = split_lines[1:]
                    else:
                        data_buf = ""
                    lines = split_lines + lines

            lines = lines[-max_lines:]
        except Exception as e:
            return {"ok": False, "code": "INTERNAL", "error": f"Failed to read log file: {e}"}

        # Redact secrets and Discord tokens
        secrets_to_redact = []
        if self.panel_secret:
            secrets_to_redact.append(self.panel_secret)
        # Parse token/secrets from config.txt without logging
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            if any(sec in k.upper() for sec in ['TOKEN', 'SECRET']):
                                val = v.strip()
                                if len(val) >= 8:
                                    secrets_to_redact.append(val)
            except Exception:
                pass

        processed_lines = []
        for line in lines:
            if level_filter and level_filter.upper() not in line.upper():
                continue
            line = clean_ansi(line)
            for s in secrets_to_redact:
                line = line.replace(s, "[REDACTED]")
            line = DISCORD_TOKEN_REGEX.sub("[REDACTED_DISCORD_TOKEN]", line)
            processed_lines.append(line)

        return {"ok": True, "data": {"lines": processed_lines}}

    async def _launcher_cookies_status(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        cookie_path = None
        for cand in [
            BOT_DIR / "cookies.txt",
            BOT_DIR / "data/cookies.txt",
            self.data_dir / "cookies.txt",
        ]:
            if cand.exists():
                cookie_path = cand
                break

        if not cookie_path:
            return {
                "ok": True,
                "data": {
                    "exists": False,
                    "path": str(BOT_DIR / "cookies.txt"),
                    "size": 0,
                    "modified": None,
                    "youtubeCookieCount": 0,
                    "earliestImportantExpiry": None,
                    "daysLeft": None
                }
            }

        st = cookie_path.stat()
        yt_count = 0
        earliest_expiry = None

        try:
            with open(cookie_path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    fields = line.split('\t')
                    if len(fields) >= 7:
                        domain, _, path, secure, expiry_str, name, val = fields[:7]
                        if "youtube.com" in domain:
                            yt_count += 1
                            if name in IMPORTANT_COOKIE_NAMES:
                                try:
                                    exp = int(expiry_str)
                                    if exp > 0:
                                        if earliest_expiry is None or exp < earliest_expiry:
                                            earliest_expiry = exp
                                except ValueError:
                                    pass
        except Exception as e:
            logger.warning(f"Error parsing cookies.txt: {e}")

        now = time.time()
        days_left = max(0, int((earliest_expiry - now) / 86400)) if earliest_expiry else None

        return {
            "ok": True,
            "data": {
                "exists": True,
                "path": str(cookie_path),
                "size": st.st_size,
                "modified": st.st_mtime,
                "youtubeCookieCount": yt_count,
                "earliestImportantExpiry": earliest_expiry,
                "daysLeft": days_left
            }
        }

    async def _launcher_cookies_get(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        cookie_path = None
        for cand in [
            BOT_DIR / "cookies.txt",
            BOT_DIR / "data/cookies.txt",
            self.data_dir / "cookies.txt",
        ]:
            if cand.exists():
                cookie_path = cand
                break

        if not cookie_path:
            return {"ok": True, "data": {"exists": False, "content": ""}}

        try:
            with open(cookie_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            return {"ok": True, "data": {"exists": True, "content": content}}
        except Exception as e:
            return {"ok": False, "code": "INTERNAL", "error": f"Error reading cookies: {str(e)}"}

    async def _launcher_cookies_set(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        text = str(params.get("text", ""))
        if not text or len(text.encode('utf-8')) > 256 * 1024:
            return {"ok": False, "code": "BAD_REQUEST", "error": "Cookie content must be between 1 and 262144 bytes"}

        # Validate Netscape format
        lines = text.strip().splitlines()
        yt_rows = 0
        for idx, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            fields = line.split('\t')
            if len(fields) < 7:
                return {
                    "ok": False,
                    "code": "BAD_REQUEST",
                    "error": f"Invalid Netscape cookie line {idx + 1}: expected 7 tab-separated fields"
                }
            if "youtube.com" in fields[0]:
                yt_rows += 1

        if yt_rows == 0:
            return {
                "ok": False,
                "code": "BAD_REQUEST",
                "error": "Cookies must contain at least one row for .youtube.com"
            }

        target_file = BOT_DIR / "cookies.txt"
        backup_file = BOT_DIR / "cookies.txt.bak"

        # Backup existing
        if target_file.exists():
            shutil.copy2(target_file, backup_file)

        # Atomic replace
        tmp_file = target_file.with_suffix('.tmp')
        with open(tmp_file, 'w', encoding='utf-8') as f:
            f.write(text.strip() + "\n")
        os.chmod(tmp_file, 0o600)
        tmp_file.replace(target_file)
        os.chmod(target_file, 0o600)

        return {"ok": True, "data": {"restartRecommended": False}}

    async def _launcher_settings_get(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        settings: Dict[str, str] = {}
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        if k in SETTING_WHITELIST:
                            settings[k] = v.strip()
        return {"ok": True, "data": settings}

    async def _launcher_settings_set(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        values = params.get("values")
        if not isinstance(values, dict):
            return {"ok": False, "code": "BAD_REQUEST", "error": "Values object required"}

        # Validate whitelist
        clean_values: Dict[str, str] = {}
        for k, v in values.items():
            if k not in SETTING_WHITELIST:
                return {"ok": False, "code": "BAD_REQUEST", "error": f"Setting key not allowed: {k}"}
            clean_values[k] = str(v).strip()

        if not self.config_path.exists():
            return {"ok": False, "code": "NOT_FOUND", "error": "config.txt not found"}

        # Backup config
        backup_path = self.config_path.with_suffix('.txt.bak')
        shutil.copy2(self.config_path, backup_path)

        # Read and modify lines
        lines: List[str] = []
        with open(self.config_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        modified_keys = set()
        new_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and '=' in stripped:
                k, _ = stripped.split('=', 1)
                k = k.strip()
                if k in clean_values:
                    new_lines.append(f"{k}={clean_values[k]}\n")
                    modified_keys.add(k)
                    continue
            new_lines.append(line)

        # Append missing keys
        for k, v in clean_values.items():
            if k not in modified_keys:
                new_lines.append(f"{k}={v}\n")

        # Atomic write
        tmp_config = self.config_path.with_suffix('.tmp')
        with open(tmp_config, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        tmp_config.replace(self.config_path)

        # Reload settings in launcher
        self.load_settings()

        return {"ok": True, "data": {"restartRequired": True}}

    def _safe_playlist_path(self, playlist_name: str) -> Path:
        """Resolves and validates playlist path inside playlists_dir."""
        name = playlist_name.strip()
        if not PLAYLIST_NAME_REGEX.match(name) or name in ('.', '..'):
            raise ValueError(f"Invalid playlist name: {name}")
        path = (self.playlists_dir / name).resolve()
        if not path.is_relative_to(self.playlists_dir):
            raise ValueError("Path traversal attempt detected")
        return path

    def _safe_track_path(self, playlist_name: str, filename: str) -> Path:
        """Resolves and validates track path inside playlist dir."""
        pl_path = self._safe_playlist_path(playlist_name)
        base = Path(filename).name.strip()
        base = re.sub(r'[\x00-\x1f\x7f]', '', base)
        if len(base) > 128 or not base:
            raise ValueError("Invalid track filename")
        ext = Path(base).suffix.lower()
        if ext not in self.supported_formats:
            raise ValueError(f"Unsupported audio format: {ext}")
        track_path = (pl_path / base).resolve()
        if not track_path.is_relative_to(pl_path):
            raise ValueError("Path traversal attempt detected")
        return track_path

    async def _launcher_playlists_create(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name", "")
        try:
            path = self._safe_playlist_path(name)
        except ValueError as e:
            return {"ok": False, "code": "BAD_REQUEST", "error": str(e)}

        if path.exists():
            return {"ok": False, "code": "BAD_REQUEST", "error": f"Playlist '{name}' already exists"}

        path.mkdir(parents=True, exist_ok=True)
        await self._trigger_child_reload()
        return {"ok": True, "data": {"name": name}}

    async def _launcher_playlists_rename(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name", "")
        new_name = params.get("newName", "")
        try:
            old_path = self._safe_playlist_path(name)
            new_path = self._safe_playlist_path(new_name)
        except ValueError as e:
            return {"ok": False, "code": "BAD_REQUEST", "error": str(e)}

        if not old_path.exists():
            return {"ok": False, "code": "NOT_FOUND", "error": f"Playlist '{name}' not found"}
        if new_path.exists():
            return {"ok": False, "code": "BAD_REQUEST", "error": f"Playlist '{new_name}' already exists"}

        old_path.rename(new_path)
        await self._trigger_child_reload()
        return {"ok": True, "data": {"name": new_name}}

    async def _launcher_playlists_delete(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name", "")
        try:
            path = self._safe_playlist_path(name)
        except ValueError as e:
            return {"ok": False, "code": "BAD_REQUEST", "error": str(e)}

        if not path.exists():
            return {"ok": False, "code": "NOT_FOUND", "error": f"Playlist '{name}' not found"}

        shutil.rmtree(path)
        await self._trigger_child_reload()
        return {"ok": True, "data": {}}

    async def _launcher_tracks_delete(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        playlist = params.get("playlist", "")
        filename = params.get("file", "")
        try:
            track_path = self._safe_track_path(playlist, filename)
        except ValueError as e:
            return {"ok": False, "code": "BAD_REQUEST", "error": str(e)}

        if not track_path.exists():
            return {"ok": False, "code": "NOT_FOUND", "error": f"File '{filename}' not found"}

        track_path.unlink()
        await self._trigger_child_reload()
        return {"ok": True, "data": {}}

    async def _launcher_playlists_inspect_youtube(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = str(params.get("url", "")).strip()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            return {"ok": False, "code": "BAD_REQUEST", "error": "A valid YouTube URL is required"}

        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--flat-playlist",
            "-J",
            "--no-warnings"
        ]
        cookie_file = BOT_DIR / "cookies.txt"
        if cookie_file.exists():
            cmd.extend(["--cookies", str(cookie_file)])

        cmd.append(url)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="replace").strip()
                first_err = [line for line in err_text.splitlines() if "ERROR:" in line]
                clean_msg = first_err[0] if first_err else "Failed to inspect YouTube URL"
                return {"ok": False, "code": "BAD_REQUEST", "error": clean_msg}

            data = json.loads(stdout.decode("utf-8", errors="replace"))
            is_playlist = (data.get("_type") == "playlist")

            if is_playlist:
                raw_entries = data.get("entries") or []
                videos = []
                for idx, e in enumerate(raw_entries, start=1):
                    if not e or not isinstance(e, dict):
                        continue
                    v_id = e.get("id") or e.get("url") or ""
                    v_title = e.get("title") or f"Track {idx}"
                    v_dur = e.get("duration")
                    v_url = e.get("url")
                    if v_url and not (v_url.startswith("http://") or v_url.startswith("https://")):
                        v_url = f"https://www.youtube.com/watch?v={v_url}"
                    elif not v_url and v_id:
                        v_url = f"https://www.youtube.com/watch?v={v_id}"

                    videos.append({
                        "id": v_id,
                        "title": v_title,
                        "duration": v_dur,
                        "url": v_url
                    })

                return {
                    "ok": True,
                    "data": {
                        "isPlaylist": True,
                        "title": data.get("title") or "YouTube Playlist",
                        "count": len(videos),
                        "videos": videos
                    }
                }
            else:
                v_id = data.get("id") or ""
                v_title = data.get("title") or "YouTube Video"
                v_dur = data.get("duration")
                v_url = f"https://www.youtube.com/watch?v={v_id}" if v_id else url

                return {
                    "ok": True,
                    "data": {
                        "isPlaylist": False,
                        "title": v_title,
                        "count": 1,
                        "videos": [{
                            "id": v_id,
                            "title": v_title,
                            "duration": v_dur,
                            "url": v_url
                        }]
                    }
                }
        except Exception as e:
            logger.error(f"Error inspecting YouTube link: {e}", exc_info=True)
            return {"ok": False, "code": "INTERNAL", "error": f"Error inspecting YouTube link: {str(e)}"}

    async def _launcher_playlists_import_youtube(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = str(params.get("url", "")).strip()
        urls_param = params.get("urls")
        pl_name = str(params.get("playlist", "")).strip()

        if isinstance(urls_param, list) and len(urls_param) > 0:
            clean_urls = [str(u).strip() for u in urls_param if str(u).strip().startswith("http")]
            if not clean_urls:
                return {"ok": False, "code": "BAD_REQUEST", "error": "No valid URLs provided in selection"}
        elif url and (url.startswith("http://") or url.startswith("https://")):
            clean_urls = [url]
        else:
            return {"ok": False, "code": "BAD_REQUEST", "error": "A valid YouTube URL or list of URLs is required"}

        if not pl_name:
            return {"ok": False, "code": "BAD_REQUEST", "error": "Playlist name is required"}

        try:
            target_dir = self._safe_playlist_path(pl_name)
        except ValueError as e:
            return {"ok": False, "code": "BAD_REQUEST", "error": str(e)}

        target_dir.mkdir(parents=True, exist_ok=True)
        asyncio.create_task(self._run_youtube_import(clean_urls, target_dir, pl_name))
        return {"ok": True, "data": {"playlist": pl_name, "count": len(clean_urls), "message": f"Import of {len(clean_urls)} items started in background"}}

    async def _run_youtube_import(self, urls: List[str], target_dir: Path, playlist_name: str):
        logger.info(f"Starting YouTube import into playlist '{playlist_name}': {len(urls)} items")
        batch_file = None
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--no-warnings",
            "--newline",
            "--restrict-filenames",
            "-o", str(target_dir / "%(title)s.%(ext)s")
        ]

        cookie_file = BOT_DIR / "cookies.txt"
        if cookie_file.exists():
            cmd.extend(["--cookies", str(cookie_file)])

        if len(urls) > 1:
            import tempfile
            with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as bf:
                for u in urls:
                    bf.write(u + "\n")
                batch_file = bf.name
            cmd.extend(["--batch-file", batch_file])
        else:
            cmd.append(urls[0])

        await self.send_panel({
            "t": "evt",
            "kind": "download_progress",
            "guildId": None,
            "data": {
                "playlist": playlist_name,
                "status": "starting",
                "message": f"Starting download of {len(urls)} tracks for playlist '{playlist_name}'..."
            }
        })

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )

            last_msg = ""
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                if "[download]" in line_str or "[ExtractAudio]" in line_str or "[youtube" in line_str:
                    last_msg = line_str
                    await self.send_panel({
                        "t": "evt",
                        "kind": "download_progress",
                        "guildId": None,
                        "data": {
                            "playlist": playlist_name,
                            "status": "downloading",
                            "message": line_str
                        }
                    })

            await proc.wait()

            if proc.returncode == 0:
                logger.info(f"YouTube import into '{playlist_name}' completed successfully.")
                await self._trigger_child_reload()
                await self.send_panel({
                    "t": "evt",
                    "kind": "download_progress",
                    "guildId": None,
                    "data": {
                        "playlist": playlist_name,
                        "status": "completed",
                        "message": f"Import into '{playlist_name}' completed successfully!"
                    }
                })
            else:
                logger.error(f"YouTube import failed with exit code {proc.returncode}: {last_msg}")
                await self.send_panel({
                    "t": "evt",
                    "kind": "download_progress",
                    "guildId": None,
                    "data": {
                        "playlist": playlist_name,
                        "status": "error",
                        "message": f"Import failed: {last_msg or f'exit code {proc.returncode}'}"
                    }
                })
        except Exception as e:
            logger.error(f"Error running YouTube import: {e}", exc_info=True)
            await self.send_panel({
                "t": "evt",
                "kind": "download_progress",
                "guildId": None,
                "data": {
                    "playlist": playlist_name,
                    "status": "error",
                    "message": f"Import error: {str(e)}"
                }
            })
        finally:
            if batch_file and os.path.exists(batch_file):
                try:
                    os.unlink(batch_file)
                except Exception:
                    pass

    async def _trigger_child_reload(self):
        """Notifies child to reload playlists cache."""
        try:
            await self._call_ipc("playlists.reload", "0", None, {})
        except Exception:
            pass

    # -------------------------------------------------------------
    # Upload Streaming & Binary Frames (§5)
    # -------------------------------------------------------------

    async def _launcher_upload_begin(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        playlist = params.get("playlist", "")
        filename = params.get("filename", "")
        size = int(params.get("size", 0))

        if len(self._active_uploads) >= 3:
            return {"ok": False, "code": "BAD_REQUEST", "error": "Maximum 3 concurrent uploads reached"}

        if size > self.max_upload_mb * 1024 * 1024:
            return {"ok": False, "code": "BAD_REQUEST", "error": f"File size exceeds maximum {self.max_upload_mb} MB"}

        try:
            target_path = self._safe_track_path(playlist, filename)
        except ValueError as e:
            return {"ok": False, "code": "BAD_REQUEST", "error": str(e)}

        upload_id = str(uuid.uuid4())
        part_path = target_path.parent / f"{target_path.name}.part"

        try:
            f = open(part_path, "wb")
        except Exception as e:
            return {"ok": False, "code": "INTERNAL", "error": f"Cannot create temporary file: {e}"}

        self._active_uploads[upload_id] = {
            "file": f,
            "part_path": part_path,
            "target_path": target_path,
            "expected_size": size,
            "received_bytes": 0,
            "last_ack_bytes": 0,
            "hasher": hashlib.sha256(),
            "overwrite": bool(params.get("overwrite", False))
        }

        return {"ok": True, "data": {"uploadId": upload_id}}

    async def _handle_binary_frame(self, data: bytes):
        """Processes upload chunk: first 36 bytes = uploadId UUID, remainder = chunk."""
        if len(data) < 36:
            return
        upload_id = data[:36].decode("ascii", errors="ignore")
        chunk = data[36:]

        session = self._active_uploads.get(upload_id)
        if not session:
            return

        session["file"].write(chunk)
        session["hasher"].update(chunk)
        session["received_bytes"] += len(chunk)

        # Send ack every 1 MB
        if session["received_bytes"] - session["last_ack_bytes"] >= 1024 * 1024:
            session["last_ack_bytes"] = session["received_bytes"]
            await self.send_panel({
                "t": "ack",
                "uploadId": upload_id,
                "received": session["received_bytes"]
            })

    async def _launcher_upload_end(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        upload_id = params.get("uploadId", "")
        expected_sha256 = params.get("sha256", "").lower()

        session = self._active_uploads.pop(upload_id, None)
        if not session:
            return {"ok": False, "code": "NOT_FOUND", "error": "Upload session not found"}

        session["file"].close()
        actual_sha256 = session["hasher"].hexdigest().lower()

        if expected_sha256 and actual_sha256 != expected_sha256:
            session["part_path"].unlink(missing_ok=True)
            return {"ok": False, "code": "BAD_REQUEST", "error": "SHA-256 verification failed"}

        target_path: Path = session["target_path"]
        if target_path.exists() and not session["overwrite"]:
            session["part_path"].unlink(missing_ok=True)
            return {"ok": False, "code": "BAD_REQUEST", "error": f"File '{target_path.name}' already exists"}

        session["part_path"].replace(target_path)
        await self._trigger_child_reload()

        return {"ok": True, "data": {"filename": target_path.name}}

    async def _launcher_upload_abort(self, user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        upload_id = params.get("uploadId", "")
        session = self._active_uploads.pop(upload_id, None)
        if session:
            session["file"].close()
            session["part_path"].unlink(missing_ok=True)
        return {"ok": True, "data": {}}

    def _abort_all_uploads(self):
        """Cleans up active uploads on disconnect."""
        for upload_id, session in list(self._active_uploads.items()):
            try:
                session["file"].close()
                session["part_path"].unlink(missing_ok=True)
            except Exception:
                pass
        self._active_uploads.clear()

    # -------------------------------------------------------------
    # Main Entry Loop & Signal Handling
    # -------------------------------------------------------------

    async def run(self):
        """Main async entrypoint."""
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self._shutdown(s)))
        except (NotImplementedError, AttributeError):
            # Windows asyncio event loop does not support add_signal_handler
            pass

        if self.autostart:
            await self.start_child()

        if self.panel_enabled:
            await self.run_panel_ws()
        else:
            # Standalone launcher: keep running until signal
            while not self._stopping_launcher:
                await asyncio.sleep(1.0)

    async def _shutdown(self, sig):
        """Graceful shutdown handler for launcher."""
        if self._stopping_launcher:
            return
        logger.info(f"Received signal {sig.name}. Shutting down launcher...")
        self._stopping_launcher = True

        self._abort_all_uploads()

        if self._events_relay_task:
            self._events_relay_task.cancel()

        if self._ws and not self._ws.closed:
            await self._ws.close()

        await self.stop_child()

        loop = asyncio.get_running_loop()
        loop.stop()


def main():
    parser = argparse.ArgumentParser(description="DiscordMusicBot Process Launcher & Panel Bridge")
    parser.add_argument("--config", default="config.txt", help="Path to config file (default: config.txt)")
    parser.add_argument("--no-autostart", action="store_true", help="Do not autostart bot child process on launch")
    args = parser.parse_args()

    launcher = BotLauncher(config_file=args.config, autostart=not args.no_autostart)
    try:
        asyncio.run(launcher.run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
