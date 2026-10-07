import chess

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}
SAC_PV_PLIES = 4


def material(board, color):
    total = 0
    for piece_type, value in PIECE_VALUES.items():
        total += value * len(board.pieces(piece_type, color))
        total -= value * len(board.pieces(piece_type, not color))
    return total


def ply_features(fen_before, uci, before, after, played_cp=None):
    board = chess.Board(fen_before)
    mover = board.turn
    legal_count = board.legal_moves.count()
    lines = before["lines"]
    best = lines[0]
    second = lines[1] if len(lines) > 1 else None
    if uci == best["uci"]:
        played_cp = best["cp"]
    elif played_cp is None and second is not None and uci == second["uci"]:
        played_cp = second["cp"]
    elif played_cp is None:
        played_cp = -after["cp"]
    material_before = material(board, mover)
    board.push(chess.Move.from_uci(uci))
    replies = after["lines"][0]["pv"][:SAC_PV_PLIES] if after["lines"] else []
    for reply in replies:
        board.push(chess.Move.from_uci(reply))
    material_after = material(board, mover)
    return {
        "legal_count": legal_count,
        "best_uci": best["uci"],
        "best_cp": best["cp"],
        "second_cp": second["cp"] if second is not None else None,
        "played_cp": played_cp,
        "is_best": uci == best["uci"],
        "sacrifice": material_before - material_after,
        "cp_white": played_cp if mover == chess.WHITE else -played_cp,
    }
