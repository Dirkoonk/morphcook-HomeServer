"""MorphCook home-server storage API.

Tiny stdlib-only key/value + blob store backing the web build, so every
device in the home network sees the same data. Persists to SQLite.

  GET    /api/state          -> {"kv": {key: text}, "images": [id, ...]}
  PUT    /api/kv/<key>       body = text
  POST   /api/kv             body = JSON {key: text, ...} (atomic batch)
  DELETE /api/kv/<key>
  GET    /api/image/<id>     -> bytes
  PUT    /api/image/<id>     body = bytes
  POST   /api/images         body = JSON {id: base64, ...} (atomic batch)
  POST   /api/images/delete  body = JSON [id, ...]
  POST   /api/clear
"""
import base64
import json
import os
import re
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

DB_PATH = os.environ.get("MORPHCOOK_DB", "/data/morphcook.db")
PORT = int(os.environ.get("PORT", "8080"))
MAX_BODY = 64 * 1024 * 1024
KEY_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")

_lock = threading.Lock()
_db = sqlite3.connect(DB_PATH, check_same_thread=False)
_db.execute("PRAGMA journal_mode=WAL")
_db.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
_db.execute("CREATE TABLE IF NOT EXISTS img (id TEXT PRIMARY KEY, b BLOB NOT NULL)")
_db.commit()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code=200, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode())

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("too large")
        return self.rfile.read(n)

    def _name(self, prefix):
        name = unquote(self.path[len(prefix):].split("?")[0])
        if not KEY_RE.match(name):
            raise ValueError("bad key")
        return name

    def _route(self, method):
        path = self.path.split("?")[0]
        try:
            with _lock:
                self._dispatch(method, path)
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "bad request"}, 400)
        except Exception:
            self._json({"error": "server error"}, 500)

    def _dispatch(self, method, path):
        if method == "GET" and path == "/api/state":
            kv = dict(_db.execute("SELECT k, v FROM kv"))
            images = [r[0] for r in _db.execute("SELECT id FROM img")]
            return self._json({"kv": kv, "images": images})
        if path.startswith("/api/kv/"):
            key = self._name("/api/kv/")
            if method == "PUT":
                _db.execute("REPLACE INTO kv VALUES (?, ?)",
                            (key, self._body().decode("utf-8")))
            elif method == "DELETE":
                _db.execute("DELETE FROM kv WHERE k = ?", (key,))
            else:
                return self._json({"error": "method"}, 405)
            _db.commit()
            return self._json({"ok": True})
        if method == "POST" and path == "/api/kv":
            items = json.loads(self._body())
            for k in items:
                if not KEY_RE.match(k):
                    raise ValueError("bad key")
            _db.executemany("REPLACE INTO kv VALUES (?, ?)", list(items.items()))
            _db.commit()
            return self._json({"ok": True})
        if path.startswith("/api/image/"):
            iid = self._name("/api/image/")
            if method == "GET":
                row = _db.execute("SELECT b FROM img WHERE id = ?", (iid,)).fetchone()
                if row is None:
                    return self._json({"error": "not found"}, 404)
                return self._send(200, bytes(row[0]), "application/octet-stream")
            if method == "PUT":
                _db.execute("REPLACE INTO img VALUES (?, ?)", (iid, self._body()))
                _db.commit()
                return self._json({"ok": True})
            if method == "DELETE":
                _db.execute("DELETE FROM img WHERE id = ?", (iid,))
                _db.commit()
                return self._json({"ok": True})
        if method == "POST" and path == "/api/images":
            items = json.loads(self._body())
            rows = []
            for k, v in items.items():
                if not KEY_RE.match(k):
                    raise ValueError("bad key")
                rows.append((k, base64.b64decode(v)))
            _db.executemany("REPLACE INTO img VALUES (?, ?)", rows)
            _db.commit()
            return self._json({"ok": True})
        if method == "POST" and path == "/api/images/delete":
            ids = json.loads(self._body())
            _db.executemany("DELETE FROM img WHERE id = ?", [(i,) for i in ids])
            _db.commit()
            return self._json({"ok": True})
        if method == "POST" and path == "/api/clear":
            _db.execute("DELETE FROM kv")
            _db.execute("DELETE FROM img")
            _db.commit()
            return self._json({"ok": True})
        self._json({"error": "not found"}, 404)

    def do_GET(self): self._route("GET")
    def do_PUT(self): self._route("PUT")
    def do_POST(self): self._route("POST")
    def do_DELETE(self): self._route("DELETE")


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
