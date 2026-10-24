#!/usr/bin/env python3
"""cdp-broker — an agent's Chrome with no open DevTools port: Chrome speaks CDP over a pipe to this broker only.

    cdp-broker AGENT          (browser-owner starts it for an agent with "cdp": "pipe" in browsers.json)

Chrome's --remote-debugging-port answers anyone on the machine who connects to it: every local program, every macOS user.
In pipe mode the agent's Chrome is started with --remote-debugging-pipe, and the broker is the only one holding the pipe:
    $RAINBOW_HOME/cdp/AGENT/cdp.sock    a unix socket (folder 0700, socket 0600) — RainbowOMMA's own tools connect here
    127.0.0.1:PORT                      the agent's CDP port, for its MCP server — a WebSocket only at
                                        /devtools/browser/<token>; /json/* and any other path are refused
    $RAINBOW_HOME/cdp/AGENT/token       that token (0600, kept across restarts); `browser-owner mcp-config AGENT` hands it out
Several clients share the one pipe: their request ids are mapped, and events go to the client whose session they belong
to (others are broadcast). When Chrome exits the broker exits; when the broker is stopped, Chrome's pipe closes.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.machinery
import importlib.util
import itertools
import json
import os
import secrets
import select
import socket
import struct
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_MSG = 32 * 1024 * 1024
WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
LOCAL_PATH = "/devtools/browser/rainbowomma"
CHROME_CMD = None                 # tests replace it: (agent row) -> argv of a fake Chrome that speaks CDP on fds 3/4


def folder(shared, agent):
    return Path(shared) / "cdp" / agent


def socket_path(shared, agent):
    return folder(shared, agent) / "cdp.sock"


def token_path(shared, agent):
    return folder(shared, agent) / "token"


def read_token(shared, agent):
    try:
        return token_path(shared, agent).read_text().strip()
    except OSError:
        return ""


def ensure_token(shared, agent):
    """the agent's token, made once (0600, in a 0700 folder) — an MCP config made with it keeps working after a restart"""
    d = folder(shared, agent)
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    try:
        fd = os.open(str(token_path(shared, agent)), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(secrets.token_urlsafe(24))
    except FileExistsError:
        pass
    return read_token(shared, agent)


class Client:
    """one WebSocket client of the broker (an MCP server, browser-owner …)"""
    def __init__(self, sock):
        self.sock, self.lock, self.open = sock, threading.Lock(), True

    def send(self, obj):
        data = json.dumps(obj).encode()
        n = len(data)
        hdr = bytes([0x81]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack(">H", n) if n < 65536 else bytes([127]) + struct.pack(">Q", n))
        with self.lock:
            try:
                self.sock.sendall(hdr + data)
            except OSError:
                self.open = False


class Broker:
    def __init__(self, a, shared):
        self.a, self.shared = a, Path(shared)
        self.clients, self.pending, self.owner = set(), {}, {}       # pending: gid → (client, id); owner: sessionId → client
        self.ids, self.mu = itertools.count(1), threading.Lock()
        self.to_chrome, self.from_chrome, self.proc = None, None, None
        self.done = threading.Event()

    # ── Chrome ──
    def start_chrome(self):
        raw = os.pipe() + os.pipe()
        r1, w1, r2, w2 = [os.dup(x) for x in raw]
        for x in raw:
            os.close(x)

        def child():
            os.dup2(r1, 3); os.dup2(w2, 4); os.setsid()
        argv = CHROME_CMD(self.a) if CHROME_CMD else chrome_argv(self.a)
        self.proc = subprocess.Popen(argv, preexec_fn=child, close_fds=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(r1); os.close(w2)
        self.to_chrome, self.from_chrome = w1, r2

    def to_browser(self, msg):
        data = (json.dumps(msg) + "\0").encode()
        with self.mu:
            os.write(self.to_chrome, data)

    def pump_chrome(self):
        buf = b""
        while True:
            try:
                chunk = os.read(self.from_chrome, 1 << 16)
            except OSError:
                chunk = b""
            if not chunk:
                break
            buf += chunk
            while b"\0" in buf:
                one, buf = buf.split(b"\0", 1)
                try:
                    self.from_browser(json.loads(one))
                except ValueError:
                    continue
            if len(buf) > MAX_MSG:
                buf = b""
        self.done.set()

    def from_browser(self, msg):
        if "id" in msg:
            with self.mu:
                c, orig = self.pending.pop(msg["id"], (None, None))
            if c is None:
                return
            sid = (msg.get("result") or {}).get("sessionId")
            if sid:
                self.owner[sid] = c                       # Target.attachToTarget: that session is this client's
            c.send({**msg, "id": orig})
            return
        sid = msg.get("sessionId")
        if msg.get("method") == "Target.attachedToTarget":
            child_sid = (msg.get("params") or {}).get("sessionId")
            parent = self.owner.get(sid) if sid else None
            if child_sid and parent:
                self.owner[child_sid] = parent
        target = self.owner.get(sid) if sid else None
        for c in ([target] if target else list(self.clients)):
            if c.open:
                c.send(msg)

    def from_client(self, c, msg):
        if not isinstance(msg, dict) or "id" not in msg or not isinstance(msg.get("method"), str):
            return
        gid = next(self.ids)
        with self.mu:
            self.pending[gid] = (c, msg["id"])
        if msg.get("sessionId"):
            self.owner.setdefault(msg["sessionId"], c)
        out = {"id": gid, "method": msg["method"], "params": msg.get("params") or {}}
        if msg.get("sessionId"):
            out["sessionId"] = msg["sessionId"]
        self.to_browser(out)

    # ── clients ──
    def serve(self, srv, local):
        while not self.done.is_set():
            try:
                rd, _, _ = select.select([srv], [], [], 0.5)
                if not rd:
                    continue
                conn, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=self.handle, args=(conn, local), daemon=True).start()

    def handle(self, conn, local):
        try:
            conn.settimeout(10)
            req = b""
            while b"\r\n\r\n" not in req:
                chunk = conn.recv(4096)
                if not chunk or len(req) > 65536:
                    return conn.close()
                req += chunk
            head = req.split(b"\r\n\r\n", 1)[0].decode("latin-1")
            line, *hdrs = head.split("\r\n")
            parts = line.split(" ")
            path = parts[1] if len(parts) > 2 else ""
            headers = {k.strip().lower(): v.strip() for k, _, v in (h.partition(":") for h in hdrs)}
            token = read_token(self.shared, self.a["name"])
            allowed = local or (token and secrets.compare_digest(path, f"/devtools/browser/{token}"))
            if local and path.startswith("/json/version"):
                body = json.dumps({"Browser": "Chrome (RainbowOMMA pipe)", "webSocketDebuggerUrl": f"ws://localhost{LOCAL_PATH}"}).encode()
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body) + body)
                return conn.close()
            if not allowed or headers.get("upgrade", "").lower() != "websocket" or "sec-websocket-key" not in headers:
                conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return conn.close()
            acc = base64.b64encode(hashlib.sha1(headers["sec-websocket-key"].encode() + WS_GUID).digest())
            conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + acc + b"\r\n\r\n")
            conn.settimeout(None)
            c = Client(conn)
            self.clients.add(c)
            try:
                self.ws_loop(c, req.split(b"\r\n\r\n", 1)[1])
            finally:
                c.open = False
                self.clients.discard(c)
                for sid in [s for s, o in list(self.owner.items()) if o is c]:
                    self.owner.pop(sid, None)
                with self.mu:
                    for gid in [g for g, (o, _) in self.pending.items() if o is c]:
                        self.pending.pop(gid, None)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def ws_loop(self, c, rest):
        buf, frag = rest, b""

        def need(n):
            nonlocal buf
            while len(buf) < n:
                chunk = c.sock.recv(1 << 16)
                if not chunk:
                    raise OSError("closed")
                buf += chunk
            out, buf = buf[:n], buf[n:]
            return out
        while not self.done.is_set():
            b1, b2 = need(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", need(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", need(8))[0]
            if n > MAX_MSG:
                raise OSError("too large")
            mask = need(4) if b2 & 0x80 else b"\0\0\0\0"
            data = bytes(x ^ mask[i % 4] for i, x in enumerate(need(n)))
            if op == 8:
                return
            if op == 9 and len(data) < 126:                 # ping → pong
                with c.lock:
                    c.sock.sendall(bytes([0x8A, len(data)]) + data)
                continue
            if op in (0, 1):
                frag += data
                if b1 & 0x80:
                    try:
                        self.from_client(c, json.loads(frag.decode("utf-8")))
                    except ValueError:
                        pass
                    frag = b""


def chrome_argv(a):
    """the agent's Chrome on a pipe — the same flags as on a port, without the port"""
    app = Path(a.get("chrome_app") or "/Applications/Google Chrome.app")
    return [str(app / "Contents" / "MacOS" / app.name[:-4]), f"--user-data-dir={a['profile']}", "--remote-debugging-pipe",
            "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
            "--disable-features=OptimizationGuideOnDeviceModel", "--no-first-run", "--no-default-browser-check",
            "--restore-last-session", "--hide-crash-restore-bubble", f"--window-name={a['label']}-CDP"]


def run(a, shared):
    ensure_token(shared, a["name"])
    sp = socket_path(shared, a["name"])
    try:
        sp.unlink()
    except FileNotFoundError:
        pass
    old = os.umask(0o177)
    unix = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    unix.bind(str(sp))
    os.umask(old)
    unix.listen(16)
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp.bind(("127.0.0.1", int(a["port"])))
    tcp.listen(16)
    b = Broker(a, shared)
    b.start_chrome()
    threading.Thread(target=b.serve, args=(unix, True), daemon=True).start()
    threading.Thread(target=b.serve, args=(tcp, False), daemon=True).start()
    try:
        b.pump_chrome()
    finally:
        for s in (unix, tcp):
            s.close()
        try:
            sp.unlink()
        except OSError:
            pass
        if b.proc and b.proc.poll() is None:
            b.proc.terminate()
    return 0


def _browser_owner():
    loader = importlib.machinery.SourceFileLoader("rainbow_browser_owner", str(HERE / "browser-owner.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(json.dumps({"status": "failed", "why": "usage: cdp-broker AGENT"}))
        return 1
    bo = _browser_owner()
    reg = bo.registry()
    a = reg.get(argv[0].strip().lower())
    if not a or a.get("cdp") != "pipe":
        print(json.dumps({"status": "refused", "why": f"{argv[0]} is not an agent with \"cdp\": \"pipe\" in browsers.json"}))
        return 2
    try:
        return run(a, bo.SHARED)
    except OSError as exc:
        print(json.dumps({"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:200]}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
