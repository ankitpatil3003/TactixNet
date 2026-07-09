"""World bounds helpers for the grid simulation."""

from __future__ import annotations

DEFAULT_MARGIN = 0.5


def clamp_position(
    position: tuple[float, float],
    width: float,
    height: float,
    *,
    margin: float = DEFAULT_MARGIN,
) -> tuple[float, float]:
    """Keep a position inside the playable grid with an optional edge margin."""
    min_x = margin
    min_y = margin
    max_x = max(margin, width - margin)
    max_y = max(margin, height - margin)
    return (
        min(max(position[0], min_x), max_x),
        min(max(position[1], min_y), max_y),
    )


def is_in_bounds(
    position: tuple[float, float],
    width: float,
    height: float,
    *,
    margin: float = 0.0,
) -> bool:
    min_x = margin
    min_y = margin
    max_x = width - margin
    max_y = height - margin
    return min_x <= position[0] <= max_x and min_y <= position[1] <= max_y
