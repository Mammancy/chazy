from __future__ import annotations

from math import floor, sqrt


def level_number_for_xp(xp: int) -> int:
    return max(1, min(3, floor(sqrt(max(xp, 0) / 100))))


def level_label_for_xp(xp: int) -> str:
    return f"Level {level_number_for_xp(xp)}"


def next_level_xp(xp: int) -> int:
    current = level_number_for_xp(xp)
    if current >= 3:
        return max(xp, 900)
    return (current + 1) ** 2 * 100

