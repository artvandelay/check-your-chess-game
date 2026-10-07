import hashlib
import io
import json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import chess.pgn

from book import load_book
from engine import Analyzer
from fetch_game import fetch_pgn, fetch_player_games, parse_ref, player_name
from html_view import build_page
from llm import explain_ply, find_api_key
from params import DEFAULT_MODEL, DEFAULT_PARAMS, DEFAULT_PORT, OUT_DIR, PKG_DIR
from review import build_rows, summarize

HOME_PATH = PKG_DIR / "home.html"
SAVED_DIR = OUT_DIR / "saved"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
DEPTHS = (12, 16, 20)
DEFAULT_APP_DEPTH = 16
MAX_BODY = 2_000_000

jobs = {}


def read_games(pgn_text):
    games = []
    handle = io.StringIO(pgn_text)
    while True:
        game = chess.pgn.read_game(handle)
        if game is None:
            break
        if game.headers or any(game.mainline_moves()):
            games.append(game)
    return games


def game_brief(game, index):
    return {
        "index": index,
        "white": game.headers.get("White", "?"),
        "black": game.headers.get("Black", "?"),
        "date": game.headers.get("Date", ""),
        "result": game.headers.get("Result", "*"),
    }


def looks_like_pgn(text):
    head = text.lstrip()
    return head.startswith("[") or head.startswith("1.") or head.startswith("1 ")


def games_from_request(payload):
    text = (payload.get("text") or payload.get("pgn") or "").strip()
    url = (payload.get("url") or "").strip()
    game_id = str(payload.get("game_id") or "").strip()
    source = text or url or game_id
    if not source:
        raise ValueError("Paste a PGN, a chess.com link, or a game number.")
    if looks_like_pgn(source):
        pgn = source
    else:
        ref = parse_ref(source)
        if ref is None:
            raise ValueError("Paste a PGN, a chess.com link, or a game number.")
        gid, kind = ref
        pgn = fetch_pgn(gid, kind)
    games = read_games(pgn)
    if not games:
        raise ValueError("No game in that PGN.")
    return games


def review_id_for(game, depth):
    board = game.board()
    sans = []
    for move in game.mainline_moves():
        sans.append(board.san(move))
        board.push(move)
    raw = "|".join([
        str(depth),
        game.headers.get("White", ""),
        game.headers.get("Black", ""),
        game.headers.get("Date", ""),
        game.headers.get("Result", ""),
        " ".join(sans),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def saved_path(review_id):
    return SAVED_DIR / f"{review_id}.json"


def save_review(review):
    SAVED_DIR.mkdir(parents=True, exist_ok=True)
    saved_path(review["id"]).write_text(json.dumps(review), encoding="utf-8")


def adopt(review):
    current = jobs.get(review["id"])
    jobs[review["id"]] = {
        "status": "done",
        "done": len(review["plies"]),
        "total": len(review["plies"]),
        "error": None,
        "review": review,
        "model": DEFAULT_MODEL,
        "api_key": None if current is None else current["api_key"],
        "lock": threading.Lock() if current is None else current["lock"],
    }


def load_saved():
    if not SAVED_DIR.exists():
        return
    for path in SAVED_DIR.glob("*.json"):
        try:
            review = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not review.get("id") or not review.get("plies"):
            continue
        adopt(review)


def library_rows():
    rows = []
    for path in SAVED_DIR.glob("*.json") if SAVED_DIR.exists() else []:
        job = jobs.get(path.stem)
        review = job["review"] if job and job.get("review") else None
        if review is None:
            continue
        summary = review["summary"]
        rows.append({
            "id": review["id"],
            "white": summary["white"],
            "black": summary["black"],
            "result": summary["result"],
            "date": review.get("headers", {}).get("Date", ""),
            "depth": review.get("depth"),
            "moves": len(review["plies"]),
            "mtime": path.stat().st_mtime,
        })
    def date_key(row):
        date = row["date"] or ""
        if "?" in date or len(date) < 10:
            return "0000.00.00"
        return date

    rows.sort(key=lambda row: (date_key(row), row["mtime"]), reverse=True)
    for row in rows:
        del row["mtime"]
    return rows


def delete_saved(ids):
    deleted = []
    seen = set()
    root = SAVED_DIR.resolve()
    for raw in ids:
        if not isinstance(raw, str) or ID_RE.fullmatch(raw) is None or raw in seen:
            continue
        seen.add(raw)
        path = SAVED_DIR / f"{raw}.json"
        if path.resolve().parent != root:
            continue
        removed = False
        if path.is_symlink() or path.is_file():
            path.unlink()
            removed = True
        if jobs.pop(raw, None) is not None:
            removed = True
        if removed:
            deleted.append(raw)
    return deleted


def run_job(job_id, game, depth):
    job = jobs[job_id]
    analyzer = Analyzer(depth=depth)
    try:
        def progress(done, total):
            job["done"] = done
            job["total"] = total

        params = dict(DEFAULT_PARAMS)
        rows = build_rows(game, analyzer, load_book(), params, on_progress=progress)
        job["review"] = {
            "id": job_id,
            "headers": dict(game.headers),
            "summary": summarize(game, rows),
            "params": params,
            "depth": depth,
            "plies": rows,
        }
        job["status"] = "done"
        save_review(job["review"])
        print(f"job {job_id} done moves={len(rows)}", flush=True)
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        print(f"job {job_id} error {e}", flush=True)
    finally:
        analyzer.close()


def start_job(game, depth):
    job_id = review_id_for(game, depth)
    existing = jobs.get(job_id)
    if existing and existing["status"] in ("done", "running"):
        return job_id, existing["status"] == "done"
    total = sum(1 for _ in game.mainline_moves())
    jobs[job_id] = {
        "status": "running",
        "done": 0,
        "total": total,
        "error": None,
        "review": None,
        "model": DEFAULT_MODEL,
        "api_key": None,
        "lock": threading.Lock(),
    }
    threading.Thread(target=run_job, args=(job_id, game, depth), daemon=True).start()
    return job_id, False


def make_handler():
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

        def send_html(self, code, text):
            body = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                raise ValueError("bad request body")
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self.send_html(200, HOME_PATH.read_text(encoding="utf-8"))
                return
            if path == "/library":
                self.send_json(200, {"games": library_rows()})
                return
            if path.startswith("/job/"):
                job = jobs.get(path[len("/job/"):])
                if job is None:
                    self.send_json(404, {"error": "no such review"})
                    return
                self.send_json(200, {
                    "status": job["status"],
                    "done": job["done"],
                    "total": job["total"],
                    "error": job["error"],
                })
                return
            if path.startswith("/r/"):
                job_id = path[len("/r/"):].strip("/")
                job = jobs.get(job_id)
                if job is None or job["review"] is None:
                    self.send_json(404, {"error": "review is not ready"})
                    return
                self.send_html(200, build_page(job["review"], serve=True))
                return
            self.send_json(404, {"error": "not found"})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path == "/review":
                self.post_review()
                return
            if path == "/library/delete":
                self.post_delete()
                return
            if path.startswith("/r/") and path.endswith("/explain"):
                job_id = path[len("/r/"):-len("/explain")].strip("/")
                self.post_explain(job_id)
                return
            self.send_json(404, {"error": "not found"})

        def post_review(self):
            try:
                payload = self.read_json()
            except (ValueError, json.JSONDecodeError, UnicodeError):
                self.send_json(400, {"error": "bad request body"})
                return
            try:
                depth = int(payload.get("depth") or DEFAULT_APP_DEPTH)
            except (TypeError, ValueError):
                self.send_json(400, {"error": "depth must be 12, 16, or 20"})
                return
            if depth not in DEPTHS:
                self.send_json(400, {"error": "depth must be 12, 16, or 20"})
                return
            source = (payload.get("text") or payload.get("pgn") or payload.get("url") or "").strip()
            name = player_name(source) if payload.get("game_index") is None else None
            if name and parse_ref(source) is None:
                try:
                    found = fetch_player_games(name)
                except LookupError as e:
                    self.send_json(404, {"error": str(e)})
                    return
                except (OSError, ValueError, json.JSONDecodeError) as e:
                    self.send_json(400, {"error": str(e)})
                    return
                self.send_json(200, {"player": name, "games": found})
                return
            try:
                games = games_from_request(payload)
            except LookupError as e:
                self.send_json(404, {"error": str(e)})
                return
            except (ValueError, OSError) as e:
                self.send_json(400, {"error": str(e)})
                return
            index = payload.get("game_index")
            if len(games) > 1 and index is None:
                self.send_json(200, {"games": [game_brief(g, i) for i, g in enumerate(games)]})
                return
            try:
                chosen = int(index or 0)
            except (TypeError, ValueError):
                self.send_json(400, {"error": "game_index must be an integer"})
                return
            if chosen < 0 or chosen >= len(games):
                self.send_json(400, {"error": f"no game at index {chosen}"})
                return
            job_id, cached = start_job(games[chosen], depth)
            self.send_json(200, {"id": job_id, "cached": cached})

        def post_delete(self):
            try:
                payload = self.read_json()
            except (ValueError, json.JSONDecodeError, UnicodeError):
                self.send_json(400, {"error": "bad request body"})
                return
            ids = payload.get("ids") if isinstance(payload, dict) else None
            if not isinstance(ids, list):
                self.send_json(400, {"error": "ids must be a list"})
                return
            try:
                deleted = delete_saved(ids)
            except OSError as e:
                self.send_json(500, {"error": str(e)})
                return
            self.send_json(200, {"deleted": deleted})

        def post_explain(self, job_id):
            job = jobs.get(job_id)
            if job is None or job["review"] is None:
                self.send_json(404, {"error": "review is not ready"})
                return
            try:
                payload = self.read_json()
                ply = int(payload["ply"])
            except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeError):
                self.send_json(400, {"error": 'body must be {"ply": <int>}'})
                return
            rows = job["review"]["plies"]
            if ply < 0 or ply >= len(rows):
                self.send_json(400, {"error": f"no ply {ply}"})
                return
            with job["lock"]:
                row = rows[ply]
                if not row["explanation"]:
                    try:
                        if job["api_key"] is None:
                            job["api_key"] = find_api_key()
                        row["explanation"] = explain_ply(row, job["model"], job["api_key"])
                    except (RuntimeError, OSError, KeyError, IndexError, ValueError) as e:
                        self.send_json(502, {"error": str(e)})
                        return
                    save_review(job["review"])
                    print(f"explained ply {ply}", flush=True)
            self.send_json(200, {"ply": ply, "explanation": row["explanation"]})

    return Handler


def main():
    load_saved()
    httpd = ThreadingHTTPServer(("127.0.0.1", DEFAULT_PORT), make_handler())
    url = f"http://127.0.0.1:{DEFAULT_PORT}/"
    print(f"serving {url}  (Ctrl+C to stop)", flush=True)
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
