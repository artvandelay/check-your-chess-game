import html
import json
from pathlib import Path
from urllib.parse import quote

import chess
import chess.svg

from params import LABELS, PKG_DIR

TEMPLATE_PATH = PKG_DIR / "viewer.html"
PIECE_SYMBOLS = "PNBRQKpnbrqk"


def piece_uris():
    uris = {}
    for symbol in PIECE_SYMBOLS:
        svg = chess.svg.piece(chess.Piece.from_symbol(symbol))
        uris[symbol] = "data:image/svg+xml;charset=utf-8," + quote(svg)
    return uris


def pv_frames(fen, sans):
    board = chess.Board(fen)
    frames = []
    for san in sans:
        try:
            move = board.parse_san(san)
        except ValueError:
            break
        board.push(move)
        frames.append({"san": san, "uci": move.uci(), "fen": board.fen()})
    return frames


def game_key(review):
    headers = review.get("headers", {})
    return headers.get("Link") or "|".join(headers.get(k, "?") for k in ("White", "Black", "Date", "Round"))


def page_data(review, serve):
    plies = []
    for row in review["plies"]:
        item = dict(row)
        item["best_line"] = pv_frames(row["fen_before"], row["best_pv_san"])
        plies.append(item)
    start = review["plies"][0]["fen_before"] if review["plies"] else chess.STARTING_FEN
    return {
        "plies": plies,
        "summary": review["summary"],
        "start_fen": start,
        "pieces": piece_uris(),
        "labels": list(LABELS),
        "k": review.get("params", {}).get("k", 0.00368208),
        "key": game_key(review),
        "serve": bool(serve),
        "id": review.get("id"),
    }


def build_page(review, serve=False):
    data_json = json.dumps(page_data(review, serve)).replace("</", "<\\/")
    title = f'{review["summary"]["white"]} vs {review["summary"]["black"]} \u00b7 review'
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    back = '<a class="back" href="/">All games</a>' if serve else ""
    return template.replace("__TITLE__", html.escape(title)).replace("__DATA__", data_json).replace("__BACK__", back)


def render_html(review, out_path, serve=False):
    Path(out_path).write_text(build_page(review, serve), encoding="utf-8")
