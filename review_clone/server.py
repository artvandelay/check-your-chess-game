import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from html_view import build_page
from llm import explain_ply, find_api_key

MAX_BODY = 1024


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def send_json(self, code, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path not in ("/", "/index.html"):
                self.send_error(404)
                return
            body = build_page(state["review"], serve=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/explain":
                self.send_json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                self.send_json(400, {"error": "bad request body"})
                return
            try:
                ply = int(json.loads(self.rfile.read(length))["ply"])
            except (ValueError, KeyError, TypeError):
                self.send_json(400, {"error": 'body must be {"ply": <int>}'})
                return
            rows = state["review"]["plies"]
            if ply < 0 or ply >= len(rows):
                self.send_json(400, {"error": f"no ply {ply}"})
                return
            with state["lock"]:
                row = rows[ply]
                if not row["explanation"]:
                    try:
                        if state["api_key"] is None:
                            state["api_key"] = find_api_key()
                        row["explanation"] = explain_ply(row, state["model"], state["api_key"])
                    except (RuntimeError, OSError, KeyError, IndexError, ValueError) as e:
                        self.send_json(502, {"error": str(e)})
                        return
                    state["out_path"].write_text(json.dumps(state["review"], indent=2), encoding="utf-8")
                    print(f"explained ply {ply}", flush=True)
            self.send_json(200, {"ply": ply, "explanation": row["explanation"]})

    return Handler


def serve(review, out_path, model, port, open_browser=True):
    state = {"review": review, "out_path": out_path, "model": model, "api_key": None, "lock": threading.Lock()}
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    url = f"http://127.0.0.1:{port}/"
    print(f"serving {url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
