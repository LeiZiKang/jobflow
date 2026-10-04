"""Presentation of optional, user-confirmed application count targets."""


def verified_progress(metrics: dict, *, separator: str = " / ") -> str:
    count = str(metrics.get("submitted_verified", 0))
    target = metrics.get("diagnostic_sample_target")
    return count if target is None else count + separator + str(target)
