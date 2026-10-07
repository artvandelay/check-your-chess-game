import json
import os
import shutil
import threading
from pathlib import Path

import chess
import chess.engine

from params import DATA_DIR, DEFAULT_DEPTH, DEFAULT_STOCKFISH, MATE_CP

_CACHE_LOCKS = {}
_CACHE_LOCKS_GUARD = threading.Lock()


def cache_lock(path):
    key = str(path)
    with _CACHE_LOCKS_GUARD:
        lock = _CACHE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _CACHE_LOCKS[key] = lock
        return lock


def find_stockfish():
    env = os.environ.get("STOCKFISH_PATH")
    if env:
        return env
    if DEFAULT_STOCKFISH.exists():
        return str(DEFAULT_STOCKFISH)
    found = shutil.which("stockfish")
    if found:
        return found
    raise FileNotFoundError("stockfish not found; set STOCKFISH_PATH")


def terminal_cp(board):
    if board.is_checkmate():
        return -MATE_CP
    return 0


class Analyzer:
    def __init__(self, depth=DEFAULT_DEPTH, multipv=2, threads=2, hash_mb=128, cache_path=None):
        self.depth = depth
        self.multipv = multipv
        self.cache_path = Path(cache_path) if cache_path else DATA_DIR / f"engine_cache_d{depth}.jsonl"
        self.cache = {}
        self.move_cache = {}
        if self.cache_path.exists():
            with self.cache_path.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("uci"):
                        self.move_cache[(row["fen"], row["uci"])] = row
                    else:
                        self.cache[row["fen"]] = row
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_path.open("a", encoding="utf-8")
        self.write_lock = cache_lock(self.cache_path)
        self.engine = chess.engine.SimpleEngine.popen_uci(find_stockfish())
        self.engine.configure({"Threads": threads, "Hash": hash_mb})

    def _store(self, row):
        with self.write_lock:
            self.cache_file.write(json.dumps(row) + "\n")
            self.cache_file.flush()

    def analyse(self, fen):
        hit = self.cache.get(fen)
        if hit is not None:
            return hit
        board = chess.Board(fen)
        if board.is_game_over():
            row = {"fen": fen, "depth": self.depth, "cp": terminal_cp(board), "lines": []}
        else:
            infos = self.engine.analyse(board, chess.engine.Limit(depth=self.depth), multipv=self.multipv)
            lines = []
            for info in infos:
                pv = info.get("pv") or []
                if not pv:
                    continue
                cp = info["score"].relative.score(mate_score=MATE_CP)
                lines.append({"uci": pv[0].uci(), "cp": cp, "pv": [m.uci() for m in pv[:8]]})
            row = {"fen": fen, "depth": self.depth, "cp": lines[0]["cp"] if lines else 0, "lines": lines}
        self.cache[fen] = row
        self._store(row)
        return row

    def analyse_move(self, fen, uci):
        hit = self.move_cache.get((fen, uci))
        if hit is not None:
            return hit["cp"]
        board = chess.Board(fen)
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"{uci} is not legal in {fen}")
        info = self.engine.analyse(board, chess.engine.Limit(depth=self.depth), root_moves=[move])
        cp = info["score"].relative.score(mate_score=MATE_CP)
        row = {"fen": fen, "uci": uci, "depth": self.depth, "cp": cp}
        self.move_cache[(fen, uci)] = row
        self._store(row)
        return cp

    def close(self):
        self.cache_file.close()
        self.engine.quit()
