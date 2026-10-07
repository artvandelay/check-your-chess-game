# Check your chess game

Live homepage: https://artvandelay.github.io/check-your-chess-game/

That page shows the homepage. To review a game, run this on your computer.

Check your chess game reviews one chess game and labels every move.
You can start from a Chess.com name, a Chess.com link, or a PGN file.

## Run the app

You need Python 3, [uv](https://docs.astral.sh/uv/), and [Stockfish](https://stockfishchess.org/).
This repo does not include Stockfish.

1. Install Stockfish.
2. Put the `stockfish` program on `PATH`.
3. If `stockfish` is not on `PATH`, set `STOCKFISH_PATH` to that program.
   When `~/pyenv/chess-review/bin/stockfish` exists, the app uses that file.
4. Create a virtual environment with uv.
5. Install the Python package in `requirements.txt`.
6. Run the app.
7. Open http://127.0.0.1:8765/.

Environment in `~/pyenv`:

```sh
uv venv ~/pyenv/chess-review
source ~/pyenv/chess-review/bin/activate
uv pip install -r requirements.txt
python review_clone/app.py
```

Local environment:

```sh
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
python review_clone/app.py
```

The app opens a browser window. The page stays on your computer.

## Opening book

When the opening book is absent, a review still runs.
Opening moves do not get the Book label.
Run this command once:

```sh
python review_clone/book.py
```

The command downloads the Lichess opening tables.
The command writes the book under `review_clone/data/`.
Git ignores that directory.

## How to start a review

Use one of the three fields.

- Type a Chess.com name. The app loads recent games for that player.
- Paste a Chess.com link. The app loads that one game.
- Paste the PGN text. You can pick a PGN file instead. If the file holds many games, you pick the game.

The game list shows 10 games at a time.

**How hard it thinks** has three depths.

- **Fast** is depth 12.
- **Normal** is depth 16. Normal is the default.
- **Deep** is depth 20.

**Already reviewed** lists reviews saved on this computer.
**See review** opens a saved review.
**Delete** removes the reviews you select.

## Explain

Explain is optional.
When you click Explain, the app calls OpenRouter.
Put `OPENROUTER_API_KEY` in a `.env` file in this directory.
Do not commit `.env`. The `.gitignore` file excludes it.

## Chess.com

The Chess.com fetch uses the Chess.com public API.
The request sends a browser User-Agent.

## Command line

You can review a PGN file without the website:

```sh
python review_clone/review.py game.pgn
```

The command writes JSON and HTML under `review_clone/out/`.
Git ignores that directory.

## Test

```sh
cd review_clone
python test_core.py
```
