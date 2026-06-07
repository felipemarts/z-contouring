"""G-code parsing, formatting, and state tracking for ZAA processing.

Pure Python/numpy — no Cura dependencies. Testable standalone with pytest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

# Regex for extracting axis values from G0/G1 lines
_PARAM_RE = re.compile(r"([XYZEF])([-+]?\d*\.?\d+)")
_GCODE_CMD_RE = re.compile(r"^(G[01])\b")


@dataclass
class GCodeMove:
    """Parsed representation of a G0/G1 move."""

    x: float | None = None
    y: float | None = None
    z: float | None = None
    e: float | None = None
    f: float | None = None
    command: str = "G1"
    comment: str = ""
    raw: str = ""


def parse_line(line: str) -> GCodeMove | str:
    """Parse a single G-code line.

    Returns a GCodeMove for G0/G1 commands, or the original string for
    anything else (comments, M-codes, type markers, etc.).
    """
    stripped = line.strip()
    if not stripped:
        return line

    # Split off inline comment
    code_part = stripped
    comment = ""
    semicolon_idx = stripped.find(";")
    if semicolon_idx >= 0:
        code_part = stripped[:semicolon_idx].strip()
        comment = stripped[semicolon_idx:]

    # Only parse G0/G1
    cmd_match = _GCODE_CMD_RE.match(code_part)
    if cmd_match is None:
        return line

    command = cmd_match.group(1)
    move = GCodeMove(command=command, comment=comment, raw=line)

    for axis_match in _PARAM_RE.finditer(code_part):
        axis = axis_match.group(1)
        value = float(axis_match.group(2))
        if axis == "X":
            move.x = value
        elif axis == "Y":
            move.y = value
        elif axis == "Z":
            move.z = value
        elif axis == "E":
            move.e = value
        elif axis == "F":
            move.f = value

    return move


def format_move(move: GCodeMove, precision: int = 4, e_precision: int = 5) -> str:
    """Serialize a GCodeMove back to a G-code string."""
    parts = [move.command]
    if move.x is not None:
        parts.append(f"X{move.x:.{precision}f}")
    if move.y is not None:
        parts.append(f"Y{move.y:.{precision}f}")
    if move.z is not None:
        parts.append(f"Z{move.z:.{precision}f}")
    if move.e is not None:
        parts.append(f"E{move.e:.{e_precision}f}")
    if move.f is not None:
        parts.append(f"F{int(move.f)}")
    result = " ".join(parts)
    if move.comment:
        result += " " + move.comment
    return result


class GCodeState:
    """Tracks machine state as G-code lines are processed."""

    def __init__(self) -> None:
        self.x: float = 0.0
        self.y: float = 0.0
        self.z: float = 0.0
        self.e: float = 0.0
        self.f: float = 0.0
        self.nominal_z: float = 0.0
        self.current_type: str = ""
        self.layer_number: int = -1
        self.relative_extrusion: bool = False
        self._layer_z_pending: bool = False

    def update(self, line: str) -> str | None:
        """Update state from a G-code line.

        Returns the type string if a ;TYPE: marker was detected, else None.
        """
        stripped = line.strip()

        # Detect TYPE markers
        if stripped.startswith(";TYPE:"):
            self.current_type = stripped[6:]
            return self.current_type

        # Detect LAYER markers — use the current Z as nominal_z.
        # The Z is typically set by a travel move BEFORE the LAYER marker.
        # If a Z move appears after the marker, it overrides.
        if stripped.startswith(";LAYER:"):
            try:
                self.layer_number = int(stripped[7:])
            except ValueError:
                pass
            # Use current Z as nominal (set by travel before LAYER marker)
            if self.z > 0:
                self.nominal_z = self.z
            self._layer_z_pending = True
            return None

        # Detect extrusion mode
        if stripped == "M82":
            self.relative_extrusion = False
            return None
        if stripped == "M83":
            self.relative_extrusion = True
            return None

        # Parse G0/G1 moves and update position
        parsed = parse_line(line)
        if isinstance(parsed, GCodeMove):
            if parsed.x is not None:
                self.x = parsed.x
            if parsed.y is not None:
                self.y = parsed.y
            if parsed.z is not None:
                self.z = parsed.z
                # First Z after a ;LAYER: marker sets the nominal layer Z
                if self._layer_z_pending:
                    self.nominal_z = parsed.z
                    self._layer_z_pending = False
            if parsed.e is not None:
                if self.relative_extrusion:
                    self.e += parsed.e
                else:
                    self.e = parsed.e
            if parsed.f is not None:
                self.f = parsed.f

        return None


def iterate_gcode(gcode_list: list[str]) -> Iterator[tuple[int, int, str]]:
    """Iterate over gcode_list yielding (chunk_index, line_index, line).

    gcode_list is Cura's list-of-chunk-strings format. Each chunk is split
    by newlines to yield individual lines while preserving chunk structure.
    """
    for chunk_idx, chunk in enumerate(gcode_list):
        lines = chunk.split("\n")
        for line_idx, line in enumerate(lines):
            yield chunk_idx, line_idx, line
