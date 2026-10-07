from winprob import expected_points


def move_loss(feat, k):
    return max(0.0, expected_points(feat["best_cp"], k) - expected_points(feat["played_cp"], k))


def classify(feat, prev_loss, in_book, params):
    k = params["k"]
    loss = move_loss(feat, k)
    ep_best = expected_points(feat["best_cp"], k)
    ep_played = expected_points(feat["played_cp"], k)
    if in_book:
        return "Book"
    if feat["legal_count"] == 1:
        return "Forced"
    if (loss <= params["excellent"]
            and feat["sacrifice"] >= params["brilliant_min_sac"]
            and ep_played >= params["brilliant_min_ep"]
            and ep_best <= params["brilliant_max_ep"]):
        return "Brilliant"
    if feat["is_best"]:
        if feat["second_cp"] is not None and ep_best - expected_points(feat["second_cp"], k) >= params["great_gap"]:
            return "Great"
        return "Best"
    if prev_loss is not None and prev_loss >= params["miss_prev_min"] and loss >= params["miss_min"]:
        return "Miss"
    if loss < params["excellent"]:
        return "Excellent"
    if loss < params["good"]:
        return "Good"
    if loss < params["inaccuracy"]:
        return "Inaccuracy"
    if loss < params["mistake"]:
        return "Mistake"
    return "Blunder"


def book_flags(epd_keys, book):
    flags = []
    still = True
    for key in epd_keys:
        still = still and key in book
        flags.append(still)
    return flags


def label_game(feats, flags, params):
    labels = []
    losses = []
    prev = None
    for feat, flag in zip(feats, flags):
        loss = move_loss(feat, params["k"])
        labels.append(classify(feat, prev, flag, params))
        losses.append(loss)
        prev = loss
    return labels, losses
