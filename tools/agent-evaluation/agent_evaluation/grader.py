def grade(sample, item):
    # type: (dict[str, object], dict[str, object]) -> float
    raw = item["score"]
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise ValueError("invalid_imported_score")
    try:
        score = float(raw)
    except ValueError:
        raise ValueError("invalid_imported_score") from None
    if not 0 <= score <= 1:
        raise ValueError("invalid_imported_score")
    return score
