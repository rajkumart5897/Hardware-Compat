"""
gui_server.py — Local web server for hardware-compat.

Changes from v1:
  - Single instance via PID lock file (~/.config/hardware-compat/server.pid)
    If already running: focus existing browser tab instead of spawning a new server.
  - Heartbeat-based auto-shutdown: browser sends GET /api/ping every 15s.
    If no ping received for >30s the server shuts itself down.
    Configurable via settings: "shutdown_on_idle": true/false (default true),
    "idle_timeout_s": 30
  - /api/shutdown endpoint for clean shutdown from the settings page.
"""

import argparse
import json
import os
import signal
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE_DIR   = Path(__file__).parent
GUI_DIR    = BASE_DIR / "gui"
MAIN_PY    = BASE_DIR / "main.py"
STATIC_DIR = GUI_DIR / "static"
sys.path.insert(0, str(BASE_DIR))

PID_FILE = Path.home() / ".config" / "hardware-compat" / "server.pid"

# Global — updated every time /api/ping is received
_last_ping   = time.time()
_shutdown_ev = threading.Event()


# ── Single-instance lock ──────────────────────────────────────────────────────

def _write_pid(port: int):
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(f"{os.getpid()}:{port}")

def _clear_pid():
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass

def _check_existing_instance() -> int | None:
    if not PID_FILE.exists():
        return None

    try:
        pid, port = map(int, PID_FILE.read_text().strip().split(":"))
    except:
        PID_FILE.unlink(missing_ok=True)
        return None

    # Check if process exists AND is actually listening
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        return None

    # EXTRA: verify server is reachable
    import socket
    s = socket.socket()
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return port
    except:
        # process exists but server is dead → stale
        PID_FILE.unlink(missing_ok=True)
        return None

# ── Idle watchdog ─────────────────────────────────────────────────────────────

def _idle_watchdog(timeout: int):
    """
    Runs in a background thread.
    Shuts down the server if no /api/ping received within `timeout` seconds.
    """
    global _last_ping
    while not _shutdown_ev.is_set():
        time.sleep(20)
        if time.time() - _last_ping > timeout:
            print(f"\n  No browser activity for {timeout}s — shutting down.")
            _shutdown_ev.set()
            # Interrupt the main thread's serve_forever()
            def shutdown():
                server.shutdown()
                server.server_close()

            threading.Thread(target=shutdown, daemon=True).start()
            return


# ── Request handlers ──────────────────────────────────────────────────────────

import subprocess

def run_scan() -> dict:
    cmd = [sys.executable, str(MAIN_PY), "--json"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=90, cwd=str(BASE_DIR)
        )
        out = result.stdout.strip()
        if not out:
            return {"error": result.stderr.strip() or "Empty scan output"}
        return json.loads(out)
    except subprocess.TimeoutExpired:
        return {"error": "Scan timed out after 90 seconds"}
    except json.JSONDecodeError as e:
        return {"error": f"Could not parse scan output: {e}"}
    except Exception as e:
        return {"error": str(e)}

def run_monitor() -> dict:
    try:
        from hardware_compat.monitor import poll
        return poll()
    except Exception as e:
        return {"error": str(e)}

def run_smart() -> dict:
    try:
        from hardware_compat.smart import scan_disks
        return {"disks": scan_disks()}
    except Exception as e:
        return {"error": str(e), "disks": []}

def read_config() -> dict:
    from hardware_compat.config import load
    return load()

def write_config(data: dict) -> dict:
    from hardware_compat.config import save
    ok = save(data)
    return {"ok": ok}


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        if args and str(args[1]) not in ("200", "304"):
            super().log_message(fmt, *args)

    def do_GET(self):
        global _last_ping
        path = self.path.split("?")[0]

        # Heartbeat — browser calls this every 15s to signal it's still open
        if path == "/api/ping":
            _last_ping = time.time()
            self._json({"ok": True})
            return

        # Clean shutdown triggered from settings page
        if path == "/api/shutdown":
            self._json({"ok": True, "message": "Server shutting down"})

            def shutdown():
                time.sleep(2) # give the response a moment to be sent before shutting down
                self.server.shutdown()       # stops serve_forever()
                self.server.server_close()   # releases port

            threading.Thread(target=shutdown, daemon=True).start()
            return

        routes = {
            "/api/scan":    run_scan,
            "/api/monitor": run_monitor,
            "/api/smart":   run_smart,
            "/api/config":  read_config,
        }
        if path in routes:
            self._json(routes[path]())
        elif path in ("/", "/index.html"):
            self._file(GUI_DIR / "index.html", "text/html")
        elif path.startswith("/static/"):
            self._file(STATIC_DIR / path[len("/static/"):], _mime(path))
        else:
            self._404()

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/config":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json({"ok": False, "error": "Invalid JSON"}, 400)
                return
            self._json(write_config(data))
        else:
            self._404()

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, mime):
        path = Path(path)
        if not path.exists():
            self._404()
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _404(self):
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not found")


def _mime(filename):
    ext = str(filename).rsplit(".", 1)[-1].lower()
    return {
        "html": "text/html", "css": "text/css",
        "js": "application/javascript", "json": "application/json",
        "ico": "image/x-icon", "png": "image/png", "svg": "image/svg+xml",
    }.get(ext, "application/octet-stream")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(port=None, open_browser=None):
    from hardware_compat.config import load as load_cfg
    cfg = load_cfg()
    port         = port         if port         is not None else cfg["gui_port"]
    open_browser = open_browser if open_browser is not None else cfg["auto_open_browser"]
    shutdown_on_idle = cfg.get("shutdown_on_idle", True)
    idle_timeout     = cfg.get("idle_timeout_s", 30)
    url = f"http://localhost:{port}"

    # ── Single instance check ─────────────────────────────────────
    existing_port = _check_existing_instance()
    if existing_port is not None:
        existing_url = f"http://localhost:{existing_port}"
        print(f"\n  hardware-compat is already running at {existing_url}")
        print(f"  Opening browser tab instead of starting a new instance.\n")
        webbrowser.open(existing_url)
        sys.exit(0)

    # ── Start server ──────────────────────────────────────────────
    try:
        server = HTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        print(f"\n  Error: could not bind to port {port}: {e}")
        print(f"  Try a different port: hardware-compat --gui --port 7475\n")
        sys.exit(1)

    _write_pid(port)

    print(f"\n  hardware-compat GUI")
    print(f"  ───────────────────────────────────────")
    print(f"  Dashboard  →  {url}")
    print(f"  Stop       →  Ctrl+C")
    if shutdown_on_idle:
        print(f"  Auto-stop  →  {idle_timeout}s after browser closes")
    print(f"  ───────────────────────────────────────\n")

    # ── Start idle watchdog ───────────────────────────────────────
    if shutdown_on_idle:
        t = threading.Thread(target=_idle_watchdog, args=(server, idle_timeout), daemon=True)
        t.start()

    # ── Open browser ──────────────────────────────────────────────
    if open_browser:
        def _open():
            time.sleep(2) # give server a moment to start before opening the browser
            subprocess.Popen(["xdg-open", url])
        threading.Thread(target=_open, daemon=True).start()

    # ── Serve ─────────────────────────────────────────────────────
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _clear_pid()
        print("\n  hardware-compat stopped.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="gui_server")
    parser.add_argument("--port",       type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    main(port=args.port, open_browser=(False if args.no_browser else None))