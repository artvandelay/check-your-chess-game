import argparse
import collections
import json
import sys
from pathlib import Path

import chess
import chess.pgn

from book import load_book
from classify import book_flags, label_game
from coach import coach_sentence
from engine import Analyzer
from features import ply_features
from html_view import render_html
from llm import explain_ply, find_api_key
from params import DEFAULT_DEPTH, DEFAULT_MODEL, DEFAULT_PARAMS, DEFAULT_PORT, KEY_LABELS, LABELS, OUT_DIR
from server import serve
from winprob import expected_points, format_eval, move_accuracy

PV_SAN_PLIES = 6


def read_game(pgn_path, index):
    game = None
    with open(pgn_path, encoding="utf-8") as f:
        for _ in range(index + 1):
            game = chess.pgn.read_game(f)
            if game is None:
                raise SystemExit(f"no game at index {index} in {pgn_path}")
    return game


def pv_san(fen, ucis, limit=PV_SAN_PLIES):
    board = chess.Board(fen)
    out = []
    for uci in ucis[:limit]:
        move = chess.Move.from_uci(uci)
        out.append(board.san(move))
        board.push(move)
    return out


def build_rows(game, analyzer, book, params, on_progress=None):
    moves = list(game.mainline_moves())
    board = game.board()
    rows, feats, keys = [], [], []
    total = len(moves)
    for ply, move in enumerate(moves):
        fen_before = board.fen()
        side = "w" if board.turn == chess.WHITE else "b"
        move_no = board.fullmove_number
        san = board.san(move)
        uci = move.uci()
        board.push(move)
        fen_after = board.fen()
        before = analyzer.analyse(fen_before)
        after = analyzer.analyse(fen_after)
        searched = None
        if before["lines"] and uci != before["lines"][0]["uci"]:
            searched = analyzer.analyse_move(fen_before, uci)
        feat = ply_features(fen_before, uci, before, after, played_cp=searched)
        feats.append(feat)
        keys.append(board.epd())
        result = board.result() if board.is_game_over() else None
        rows.append({
            "ply": ply,
            "move_no": move_no,
            "side": side,
            "san": san,
            "uci": move.uci(),
            "fen_before": fen_before,
            "fen_after": fen_after,
            "coach_label": None,
            "coach_text": None,
            "eval": result or format_eval(feat["cp_white"]),
            "eval_cp_white": feat["cp_white"],
            "best_uci": feat["best_uci"],
            "best_san": chess.Board(fen_before).san(chess.Move.from_uci(feat["best_uci"])),
            "best_pv_san": pv_san(fen_before, before["lines"][0]["pv"]),
            "played_pv_san": pv_san(fen_after, after["lines"][0]["pv"]) if after["lines"] else [],
            "loss": None,
            "accuracy": None,
            "explanation": None,
        })
        if on_progress is not None:
            on_progress(ply + 1, total)
    flags = book_flags(keys, book)
    labels, losses = label_game(feats, flags, params)
    k = params["k"]
    for row, feat, label, loss, flag in zip(rows, feats, labels, losses, flags):
        row["coach_label"] = label
        before_white = feat["best_cp"] if row["side"] == "w" else -feat["best_cp"]
        row["coach_text"] = coach_sentence(
            row["san"], label, format_eval(before_white), row["eval"], row["best_san"], row["best_pv_san"],
        )
        row["loss"] = round(loss, 4)
        if flag:
            row["accuracy"] = 100.0
        else:
            acc = move_accuracy(expected_points(feat["best_cp"], k), expected_points(feat["played_cp"], k))
            row["accuracy"] = round(acc, 1)
    return rows


def summarize(game, rows):
    counts = {"w": collections.Counter(), "b": collections.Counter()}
    accs = {"w": [], "b": []}
    for row in rows:
        counts[row["side"]][row["coach_label"]] += 1
        accs[row["side"]].append(row["accuracy"])
    return {
        "white": game.headers.get("White", "?"),
        "black": game.headers.get("Black", "?"),
        "result": game.headers.get("Result", "*"),
        "accuracy": {side: (round(sum(v) / len(v), 1) if v else None) for side, v in accs.items()},
        "counts": {side: dict(c) for side, c in counts.items()},
    }


def explain_rows(rows, plies, model):
    try:
        api_key = find_api_key()
    except RuntimeError as e:
        print(f"explain skipped: {e}", file=sys.stderr)
        return
    for ply in plies:
        if ply < 0 or ply >= len(rows):
            print(f"explain skipped: no ply {ply}", file=sys.stderr)
            continue
        try:
            rows[ply]["explanation"] = explain_ply(rows[ply], model, api_key)
            print(f"explained ply {ply}", flush=True)
        except (OSError, KeyError, IndexError, ValueError) as e:
            print(f"explain failed ply {ply}: {e}", file=sys.stderr)


def print_review(review):
    s = review["summary"]
    print(f'{s["white"]} (accuracy {s["accuracy"]["w"]})  vs  {s["black"]} (accuracy {s["accuracy"]["b"]})  {s["result"]}')
    for label in LABELS:
        w = s["counts"]["w"].get(label, 0)
        b = s["counts"]["b"].get(label, 0)
        if w or b:
            print(f"  {label:<11} {w:>3} {b:>3}")
    for r in review["plies"]:
        num = f'{r["move_no"]}.' if r["side"] == "w" else f'{r["move_no"]}...'
        print(f'[{r["ply"]:>3}] {num:<6} {r["san"]:<8} {r["coach_label"]:<11} {r["eval"]:>7}  {r["coach_text"]}')
        if r["explanation"]:
            print("        " + r["explanation"])


def main():
    parser = argparse.ArgumentParser(description="Generate a chess.com-style Game Review from a PGN.")
    parser.add_argument("pgn")
    parser.add_argument("--game-index", type=int, default=0)
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument("--out", default=None)
    parser.add_argument("--html", default=None)
    parser.add_argument("--no-html", action="store_true")
    parser.add_argument("--explain", type=int, nargs="+", default=[], metavar="PLY")
    parser.add_argument("--explain-key", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    pgn_path = Path(args.pgn)
    stem = f"{pgn_path.stem}_{args.game_index}" if args.game_index else pgn_path.stem
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUT_DIR / f"{stem}_review.json"
    html_path = Path(args.html) if args.html else OUT_DIR / f"{stem}_review.html"

    game = read_game(pgn_path, args.game_index)
    params = dict(DEFAULT_PARAMS)
    analyzer = Analyzer(depth=args.depth)
    try:
        rows = build_rows(game, analyzer, load_book(), params)
    finally:
        analyzer.close()
    review = {
        "headers": dict(game.headers),
        "summary": summarize(game, rows),
        "params": params,
        "depth": args.depth,
        "plies": rows,
    }

    targets = set(args.explain)
    if args.explain_key:
        targets |= {r["ply"] for r in rows if r["coach_label"] in KEY_LABELS}
    if targets:
        explain_rows(rows, sorted(targets), args.model)

    out_path.write_text(json.dumps(review, indent=2), encoding="utf-8")
    if not args.no_html:
        render_html(review, html_path)
    if not args.quiet:
        print_review(review)
    print(f"wrote {out_path}")
    if not args.no_html:
        print(f"wrote {html_path}")
    if args.serve:
        serve(review, out_path, args.model, args.port, open_browser=not args.no_open)
    return 0


if __name__ == "__main__":
    sys.exit(main())
