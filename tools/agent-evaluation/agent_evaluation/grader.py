import math


def grade(sample: dict[str, object], item: dict[str, object]) -> float:
    score = item["score"]
    if type(score) not in (int, float):
        raise ValueError("invalid_imported_score")
    if not isinstance(score, int | float) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("invalid_imported_score")
    return float(score)
