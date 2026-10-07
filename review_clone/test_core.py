import tempfile
from pathlib import Path

import chess

from classify import book_flags, classify, label_game
from coach import coach_sentence
from features import material, ply_features
from fetch_game import parse_ref, pgn_from_payload
from html_view import render_html
from llm import build_prompt
from params import DEFAULT_PARAMS, coach_text
from winprob import expected_points, format_eval, move_accuracy

P = dict(DEFAULT_PARAMS)
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def feat(best_cp, played_cp, is_best=False, second_cp=None, legal=20, sac=0):
    return {"legal_count": legal, "best_uci": "e2e4", "best_cp": best_cp, "second_cp": second_cp,
            "played_cp": played_cp, "is_best": is_best, "sacrifice": sac, "cp_white": played_cp}


def test_winprob():
    assert abs(expected_points(0, P["k"]) - 0.5) < 1e-9
    assert expected_points(300, P["k"]) > expected_points(100, P["k"])
    assert expected_points(10000, P["k"]) > 0.999
    assert format_eval(0) == "0.00"
    assert format_eval(25) == "+0.25"
    assert format_eval(-148) == "-1.48"
    assert format_eval(9997) == "+M3"
    assert format_eval(-9998) == "-M2"
    assert format_eval(10000) == "1-0"
    assert move_accuracy(0.6, 0.6) > 99.9
    assert move_accuracy(0.9, 0.1) < 5


def test_classify():
    assert classify(feat(0, 0), None, True, P) == "Book"
    assert classify(feat(0, 0, legal=1), None, False, P) == "Forced"
    assert classify(feat(0, 0, is_best=True, second_cp=-10), None, False, P) == "Best"
    assert classify(feat(0, 0, is_best=True, second_cp=-400), None, False, P) == "Great"
    assert classify(feat(150, 150, is_best=True, second_cp=100, sac=3), None, False, P) == "Brilliant"
    assert classify(feat(50, 45), None, False, P) == "Excellent"
    assert classify(feat(0, -100), None, False, P) == "Inaccuracy"
    assert classify(feat(0, -200), None, False, P) == "Mistake"
    assert classify(feat(0, -500), None, False, P) == "Blunder"
    assert classify(feat(300, 0), 0.3, False, P) == "Miss"
    labels, losses = label_game([feat(0, -500), feat(300, 0)], [False, False], P)
    assert labels == ["Blunder", "Miss"], labels
    assert losses[0] > 0.3
    assert book_flags(["a", "b", "c"], {"a", "c"}) == [True, False, False]
    assert coach_text("Bg3", "Miss") == "Bg3 is a miss"


def test_features():
    assert material(chess.Board(), chess.WHITE) == 0
    before = {"cp": 30, "lines": [{"uci": "e2e4", "cp": 30, "pv": ["e2e4", "e7e5"]},
                                  {"uci": "d2d4", "cp": 25, "pv": ["d2d4"]}]}
    after = {"cp": -30, "lines": [{"uci": "e7e5", "cp": -30, "pv": ["e7e5", "g1f3"]}]}
    f = ply_features(chess.STARTING_FEN, "e2e4", before, after)
    assert f["played_cp"] == 30 and f["is_best"] and f["cp_white"] == 30, f
    assert f["legal_count"] == 20 and f["sacrifice"] == 0, f
    after_a3 = {"cp": 10, "lines": [{"uci": "e7e5", "cp": 10, "pv": ["e7e5"]}]}
    f = ply_features(chess.STARTING_FEN, "a2a3", before, after_a3)
    assert f["played_cp"] == -10 and not f["is_best"] and f["cp_white"] == -10, f
    before_b = {"cp": -20, "lines": [{"uci": "c7c5", "cp": -20, "pv": ["c7c5"]},
                                     {"uci": "e7e6", "cp": -25, "pv": ["e7e6"]}]}
    after_b = {"cp": 40, "lines": [{"uci": "g1f3", "cp": 40, "pv": ["g1f3"]}]}
    f = ply_features(AFTER_E4, "e7e5", before_b, after_b)
    assert f["played_cp"] == -40 and f["cp_white"] == 40, f


def fake_row():
    return {"ply": 0, "move_no": 1, "side": "w", "san": "e4", "uci": "e2e4",
            "fen_before": chess.STARTING_FEN, "fen_after": AFTER_E4,
            "coach_label": "Best", "coach_text": "e4 is best", "eval": "+0.30", "eval_cp_white": 30,
            "best_uci": "e2e4", "best_san": "e4", "best_pv_san": ["e4", "e5"],
            "played_pv_san": ["e5", "Nf3"], "loss": 0.0, "accuracy": 100.0, "explanation": None}


def test_html_and_prompt():
    review = {"plies": [fake_row()],
              "summary": {"white": "A", "black": "B", "result": "*",
                          "accuracy": {"w": 100.0, "b": None}, "counts": {"w": {"Best": 1}, "b": {}}}}
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "r.html"
        render_html(review, out)
        page = out.read_text(encoding="utf-8")
        assert "const DATA = {" in page and "__DATA__" not in page, "template not filled"
        assert "data:image/svg+xml" in page and '"best_line"' in page and '"serve": false' in page
    prompt = build_prompt(fake_row())
    assert '"engine_best_move": "e4"' in prompt, prompt


def test_coach_and_ref():
    assert coach_sentence("Nc6", "Book", "+0.25", "+0.25", "Nc6", ["Nc6"]) == "Nc6 is theory."
    assert coach_sentence("Kxf8", "Forced", "+4.74", "+4.74", "Kxf8", ["Kxf8"]) == "Kxf8 is the only legal move."
    assert coach_sentence("Na3", "Best", "+0.40", "+0.40", "Na3", ["Na3"]) == "Na3 keeps the position at +0.40."
    text = coach_sentence("b3", "Mistake", "+0.40", "-1.91", "Na3", ["Na3", "Na5", "b3"])
    assert text == "b3 is a mistake. It goes from +0.40 to -1.91. Best was Na3: Na3 Na5 b3.", text
    assert parse_ref("https://www.chess.com/game/live/184965551942") == ("184965551942", "live")
    assert parse_ref("https://www.chess.com/analysis/game/daily/99/review") == ("99", "daily")
    assert parse_ref("184965551942") == ("184965551942", None)
    assert parse_ref("1. e4 e5") is None
    pgn = pgn_from_payload({"game": {"moveList": "jrZJ", "pgnHeaders": {"White": "A", "Black": "B", "Result": "*"}}})
    assert "1. b3 d5" in pgn, pgn


def main():
    test_winprob()
    test_classify()
    test_features()
    test_html_and_prompt()
    test_coach_and_ref()
    print("ok")


if __name__ == "__main__":
    main()
