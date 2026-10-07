import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

import chess
import chess.pgn

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TCN_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?"
PROMO = {"q": chess.QUEEN, "n": chess.KNIGHT, "b": chess.BISHOP, "r": chess.ROOK}
LINK_RE = re.compile(r"chess\.com/(?:analysis/)?game/(live|daily)/(\d+)", re.I)
MEMBER_RE = re.compile(r"chess\.com/(?:member|play)/([A-Za-z0-9_-]+)", re.I)
USER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{2,24}$")
BARE_RE = re.compile(r"^\d{5,}$")
RESULT_WORD = {
    "win": "win",
    "checkmated": "loss",
    "resigned": "loss",
    "timeout": "loss",
    "abandoned": "loss",
    "lose": "loss",
    "agreed": "draw",
    "repetition": "draw",
    "stalemate": "draw",
    "insufficient": "draw",
    "50move": "draw",
    "timevsinsufficient": "draw",
}


def player_name(text):
    text = (text or "").strip()
    if not text or looks_like_move_text(text):
        return None
    match = MEMBER_RE.search(text)
    if match:
        return match.group(1)
    if USER_RE.match(text):
        return text
    return None


def looks_like_move_text(text):
    head = text.lstrip()
    return head.startswith("[") or head.startswith("1.") or head.startswith("1 ")


def parse_ref(text):
    text = (text or "").strip()
    match = LINK_RE.search(text)
    if match:
        return match.group(2), match.group(1).lower()
    if BARE_RE.match(text) and "[" not in text:
        return text, None
    return None


def moves_from_tcn(tcn, board):
    moves = []
    i = 0
    while i < len(tcn):
        if tcn[i] == "$":
            i += 1
            continue
        if i + 1 >= len(tcn):
            break
        try:
            origin = TCN_CHARS.index(tcn[i])
            target = TCN_CHARS.index(tcn[i + 1])
        except ValueError as e:
            raise ValueError(f"bad move encoding at {tcn[i:i+4]!r}") from e
        i += 2
        piece = board.piece_at(origin)
        promo = None
        if piece and piece.piece_type == chess.PAWN and chess.square_rank(target) in (0, 7):
            if i < len(tcn) and tcn[i] in PROMO:
                promo = PROMO[tcn[i]]
                i += 1
            else:
                promo = chess.QUEEN
        move = chess.Move(origin, target, promotion=promo)
        if piece and piece.piece_type == chess.KING:
            rook = board.piece_at(target)
            if rook and rook.piece_type == chess.ROOK and rook.color == piece.color:
                file = 6 if chess.square_file(target) > chess.square_file(origin) else 2
                move = chess.Move(origin, chess.square(file, chess.square_rank(origin)))
        if move not in board.legal_moves:
            raise ValueError(f"decoded move {move.uci()} is not legal")
        board.push(move)
        moves.append(move)
    return moves


def pgn_from_tcn(game):
    headers = game.get("pgnHeaders") or {}
    fen = headers.get("FEN") or chess.STARTING_FEN
    board = chess.Board(fen)
    moves = moves_from_tcn(game.get("moveList") or "", board)
    out = chess.pgn.Game()
    for key, value in headers.items():
        out.headers[key] = str(value)
    if "FEN" not in out.headers:
        out.headers["FEN"] = fen
    node = out
    replay = chess.Board(fen)
    for move in moves:
        node = node.add_variation(move)
        replay.push(move)
    if "Result" not in out.headers:
        out.headers["Result"] = replay.result() if replay.is_game_over() else "*"
    return str(out)


def pgn_from_payload(data):
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("pgn"), str) and data["pgn"].strip():
        return data["pgn"]
    game = data.get("game")
    if not isinstance(game, dict):
        return None
    if isinstance(game.get("pgn"), str) and game["pgn"].strip():
        return game["pgn"]
    if game.get("moveList"):
        return pgn_from_tcn(game)
    return None


def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_player_games(username, limit=25):
    name = username.strip()
    try:
        payload = get_json(f"https://api.chess.com/pub/player/{name}/games/archives")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LookupError(f"No chess.com player {name}") from e
        raise
    archives = payload.get("archives") or []
    if not archives:
        raise LookupError(f"{name} has no games")
    collected = []
    for url in reversed(archives):
        month = get_json(url).get("games") or []
        collected.extend(month)
        if len(collected) >= limit:
            break
    collected.sort(key=lambda game: game.get("end_time") or 0, reverse=True)
    rows = []
    for game in collected:
        pgn = game.get("pgn")
        if not pgn:
            continue
        white = (game.get("white") or {}).get("username") or "?"
        black = (game.get("black") or {}).get("username") or "?"
        side = game.get("white") if white.lower() == name.lower() else game.get("black")
        end = game.get("end_time")
        date = datetime.fromtimestamp(end, timezone.utc).strftime("%Y.%m.%d") if end else ""
        rows.append({
            "white": white,
            "black": black,
            "result": RESULT_WORD.get((side or {}).get("result") or "", ""),
            "date": date,
            "time_class": game.get("time_class") or "",
            "pgn": pgn,
        })
        if len(rows) >= limit:
            break
    if not rows:
        raise LookupError(f"{name} has no games")
    return rows


def fetch_pgn(game_id, kind=None, timeout=20):
    kinds = [kind] if kind else ["live", "daily"]
    last_error = None
    for one in kinds:
        url = f"https://www.chess.com/callback/{one}/game/{game_id}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as e:
            last_error = e
            continue
        pgn = pgn_from_payload(data)
        if pgn:
            return pgn
    if last_error is not None and kind is not None:
        raise LookupError(f"No game {game_id}") from last_error
    raise LookupError(f"No game {game_id}")
