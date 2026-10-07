from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parent
DATA_DIR = PKG_DIR / "data"
OUT_DIR = PKG_DIR / "out"
OPENINGS_DIR = DATA_DIR / "openings"
BOOK_PATH = DATA_DIR / "book_epd.txt"
CORPUS_PATH = REPO_ROOT / "reviews.jsonl"
DEFAULT_STOCKFISH = Path.home() / "pyenv" / "chess-review" / "bin" / "stockfish"
DEFAULT_DEPTH = 14
DEFAULT_MODEL = "anthropic/claude-sonnet-5.5"
DEFAULT_PORT = 8765
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MATE_CP = 10000

LABELS = (
    "Book", "Forced", "Brilliant", "Great", "Best", "Excellent",
    "Good", "Inaccuracy", "Mistake", "Miss", "Blunder",
)
KEY_LABELS = ("Brilliant", "Great", "Miss", "Mistake", "Blunder")

DESCRIPTION_BY_LABEL = {
    "Best": "is best",
    "Blunder": "is a blunder",
    "Book": "is a book move",
    "Brilliant": "is brilliant",
    "Excellent": "is excellent",
    "Forced": "is forced",
    "Good": "is good",
    "Great": "is a great move",
    "Inaccuracy": "is an inaccuracy",
    "Miss": "is a miss",
    "Mistake": "is a mistake",
}

DEFAULT_PARAMS = {
    "k": 0.00368208,
    "excellent": 0.02,
    "good": 0.05,
    "inaccuracy": 0.10,
    "mistake": 0.20,
    "great_gap": 0.15,
    "miss_prev_min": 0.10,
    "miss_min": 0.05,
    "brilliant_min_sac": 2,
    "brilliant_min_ep": 0.5,
    "brilliant_max_ep": 0.97,
}


def coach_text(san, label):
    phrase = DESCRIPTION_BY_LABEL.get(label)
    if phrase is None:
        return san + " (" + label + ")"
    return san + " " + phrase


def is_test_game(game_id):
    return int(game_id) % 5 == 0
