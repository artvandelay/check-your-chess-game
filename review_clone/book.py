import csv
import io
import json
import urllib.request

import chess
import chess.pgn

from params import BOOK_PATH, CORPUS_PATH, OPENINGS_DIR, is_test_game

TSV_URL = "https://raw.githubusercontent.com/lichess-org/chess-openings/master/{letter}.tsv"
LETTERS = ("a", "b", "c", "d", "e")


def download_openings():
    OPENINGS_DIR.mkdir(parents=True, exist_ok=True)
    for letter in LETTERS:
        path = OPENINGS_DIR / f"{letter}.tsv"
        if path.exists():
            continue
        with urllib.request.urlopen(TSV_URL.format(letter=letter), timeout=30) as resp:
            path.write_bytes(resp.read())


def lichess_positions():
    keys = set()
    for letter in LETTERS:
        path = OPENINGS_DIR / f"{letter}.tsv"
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                game = chess.pgn.read_game(io.StringIO(row["pgn"]))
                board = game.board()
                for move in game.mainline_moves():
                    board.push(move)
                    keys.add(board.epd())
    return keys


def corpus_book_positions(path=CORPUS_PATH):
    keys = set()
    if not path.exists():
        return keys
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("coach_label") != "Book" or is_test_game(row["game_id"]):
                continue
            keys.add(chess.Board(row["fen_after"]).epd())
    return keys


def build_book():
    download_openings()
    keys = lichess_positions() | corpus_book_positions()
    BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOOK_PATH.write_text("".join(k + "\n" for k in sorted(keys)), encoding="utf-8")
    return len(keys)


def load_book(path=BOOK_PATH):
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


if __name__ == "__main__":
    print(f"book positions {build_book()}")
