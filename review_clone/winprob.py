import math

from params import MATE_CP


def expected_points(cp, k):
    x = max(-MATE_CP, min(MATE_CP, cp))
    return 1.0 / (1.0 + math.exp(-k * x))


def move_accuracy(ep_before, ep_after):
    drop = max(0.0, (ep_before - ep_after) * 100.0)
    acc = 103.1668 * math.exp(-0.04354 * drop) - 3.1669
    return max(0.0, min(100.0, acc))


def format_eval(cp_white):
    if abs(cp_white) >= MATE_CP - 500:
        n = MATE_CP - abs(cp_white)
        if n == 0:
            return "1-0" if cp_white > 0 else "0-1"
        return ("+M" if cp_white > 0 else "-M") + str(n)
    if cp_white == 0:
        return "0.00"
    return f"{cp_white / 100:+.2f}"
