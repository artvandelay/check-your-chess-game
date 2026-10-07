PHRASE = {
    "Good": "a good move",
    "Inaccuracy": "an inaccuracy",
    "Mistake": "a mistake",
    "Miss": "a miss",
    "Blunder": "a blunder",
    "Great": "a great move",
    "Brilliant": "brilliant",
}


def coach_sentence(san, label, eval_before, eval_after, best_san, best_line):
    if label == "Book":
        return san + " is theory."
    if label == "Forced":
        return san + " is the only legal move."
    if label in ("Best", "Excellent"):
        return san + " keeps the position at " + eval_after + "."
    if label in ("Great", "Brilliant"):
        return san + " is " + PHRASE[label] + ". The evaluation is " + eval_after + "."
    phrase = PHRASE.get(label, label.lower())
    text = san + " is " + phrase + ". It goes from " + eval_before + " to " + eval_after + "."
    if best_san and best_san != san:
        line = " ".join(best_line[:4])
        text += " Best was " + best_san
        if line:
            text += ": " + line
        text += "."
    return text
