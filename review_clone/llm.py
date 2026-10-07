import json
import os
import urllib.request

from params import OPENROUTER_URL, REPO_ROOT

SYSTEM_PROMPT = (
    "You are a chess coach writing the short explanation shown next to a move in a game review. "
    "Use only the facts given. The engine lines are correct; do not claim any tactic, threat or square "
    "that the lines do not show. Write 2 or 3 plain sentences for the player who made the move. "
    "Start with the coach sentence given. Say what the move allowed or achieved, and what the best move "
    "would have done, using the given lines."
)


def find_api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key.strip()
    for folder in [REPO_ROOT, *REPO_ROOT.parents]:
        path = folder / ".env"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
            bare = line.strip('"').strip("'")
            if bare.startswith("sk-or-"):
                return bare
    raise RuntimeError("OPENROUTER_API_KEY not found in environment or any .env above the repo")


def build_prompt(row):
    facts = {
        "player": "White" if row["side"] == "w" else "Black",
        "move": f'{row["move_no"]}{"." if row["side"] == "w" else "..."} {row["san"]}',
        "coach_sentence": row["coach_text"],
        "classification": row["coach_label"],
        "position_before_fen": row["fen_before"],
        "eval_after_move_white_pov": row["eval"],
        "engine_best_move": row["best_san"],
        "best_line_from_position_before": " ".join(row["best_pv_san"]),
        "opponent_best_reply_line_after_move": " ".join(row["played_pv_san"]),
        "expected_points_lost": row["loss"],
    }
    return json.dumps(facts, indent=2)


def explain_ply(row, model, api_key, timeout=60):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(row)},
        ],
        "max_tokens": 600,
    }
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()
