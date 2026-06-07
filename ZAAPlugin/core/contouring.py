"""Z Anti-Aliasing contouring algorithm.

Subdivides extrusion segments, ray-casts to find true surface Z,
replaces flat Z with contoured values, and adjusts flow compensation.

Pure Python/numpy — no Cura dependencies.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from .gcode_parser import GCodeMove, GCodeState, format_move, parse_line

if TYPE_CHECKING:
    from .collision import CollisionChecker
    from .ray_caster import RayCaster


def subdivide_segment(
    x0: float, y0: float, x1: float, y1: float, resolution: float
) -> np.ndarray:
    """Subdivide a line segment into evenly-spaced points.

    Returns (N+1, 2) array including start and end points, where N is the
    number of sub-segments (at least 1).
    """
    length = math.hypot(x1 - x0, y1 - y0)
    n_segments = max(1, int(math.ceil(length / resolution)))
    t = np.linspace(0.0, 1.0, n_segments + 1)
    points = np.column_stack([x0 + t * (x1 - x0), y0 + t * (y1 - y0)])
    return points


def compute_contoured_moves(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    e_total: float,
    nominal_z: float,
    layer_height: float,
    max_contour: float,
    resolution: float,
    caster: RayCaster,
    collision_checker: CollisionChecker | None = None,
    feedrate: float | None = None,
) -> list[GCodeMove]:
    """Compute contoured sub-moves for a single extrusion segment.

    Args:
        x0, y0: Start position.
        x1, y1: End position.
        e_total: Total extrusion for the original segment.
        nominal_z: The layer's nominal (flat) Z height.
        layer_height: Nominal layer height setting.
        max_contour: Maximum Z drop below nominal_z.
        resolution: Subdivision spacing (mm).
        caster: RayCaster instance for surface queries.
        collision_checker: Optional collision checker.
        feedrate: Optional feedrate to include on the first sub-move.

    Returns:
        List of GCodeMove objects representing the contoured path.
    """
    points = subdivide_segment(x0, y0, x1, y1, resolution)
    n_points = len(points)

    # Batch ray-cast all sub-points (skip the first — it's the previous position)
    z_values = np.full(n_points, nominal_z)
    hit_z = caster.hit_z_batch(points)

    # Z range for contouring: allow Z to follow the surface within
    # one layer_height above and below the nominal Z.
    # The floor is the midpoint between this layer and the previous one —
    # never descend into the previous layer's territory.
    z_floor = nominal_z - max_contour * 0.5
    z_ceiling = nominal_z + max_contour

    for i in range(n_points):
        if not np.isnan(hit_z[i]):
            # Only contour if the surface is within range of this layer.
            # If the surface is far above or below, it's not the relevant
            # surface for this layer (e.g., bottom skin, internal layer).
            if hit_z[i] < z_floor or hit_z[i] > z_ceiling:
                # Surface too far from this layer — keep nominal
                z_values[i] = nominal_z
            else:
                z_values[i] = hit_z[i]

            if collision_checker is not None:
                z_values[i] = collision_checker.check_safe_z(
                    points[i, 0], points[i, 1], z_values[i]
                )

    # Smooth the Z profile: only modify points that were actually contoured
    # (not nominal). Points at nominal_z have layers above and must stay flat.
    contoured_mask = np.array([
        abs(z_values[i] - nominal_z) > 0.001 for i in range(n_points)
    ])
    contoured_indices = np.where(contoured_mask)[0]

    if len(contoured_indices) >= 2:
        # Interpolate smoothly only among contoured points
        first_c = contoured_indices[0]
        last_c = contoured_indices[-1]
        z_start = z_values[first_c]
        z_end = z_values[last_c]
        if abs(z_end - z_start) > 0.001:
            for idx in contoured_indices:
                t = (idx - first_c) / (last_c - first_c)
                z_smooth = z_start + t * (z_end - z_start)
                if z_end < z_start:
                    z_values[idx] = min(z_values[idx], z_smooth)
                else:
                    z_values[idx] = max(z_values[idx], z_smooth)

    # Skip contouring if Z doesn't vary along the segment AND is at the
    # max_contour limit. This catches lateral wall segments where all sub-points
    # hit the same low Z on a nearby surface — contouring them would drag
    # the entire wall down to a constant wrong Z.
    # We allow uniform-Z contouring when the Z is between nominal and
    # nominal - max_contour (the surface is genuinely flat but lower).
    z_min = z_values.min()
    z_max = z_values.max()
    all_at_floor = abs(z_min - (nominal_z - max_contour)) < 0.001
    if z_max - z_min < 0.001 and all_at_floor:
        # All points clamped to max_contour floor — likely a lateral wall
        # passing over a lower surface. Don't contour.
        move = GCodeMove(command="G1", x=x1, y=y1, z=nominal_z, e=e_total)
        if feedrate is not None:
            move.f = feedrate
        return [move]

    # Compute per-sub-segment distances for E distribution
    deltas = np.diff(points, axis=0)  # (N, 2)
    seg_lengths = np.sqrt(deltas[:, 0] ** 2 + deltas[:, 1] ** 2)
    total_length = seg_lengths.sum()

    if total_length < 1e-10:
        # Zero-length segment: emit single move
        move = GCodeMove(command="G1", x=x1, y=y1, z=z_values[-1], e=e_total)
        if feedrate is not None:
            move.f = feedrate
        return [move]

    # Compute E per sub-segment with flow compensation
    moves: list[GCodeMove] = []
    for i in range(1, n_points):
        fraction = seg_lengths[i - 1] / total_length

        # Local layer height: how much material height at this point
        # nominal_z is the top of the nominal layer; z_values[i] is where we print
        # If we drop by delta_z, the local layer height decreases
        delta_z = nominal_z - z_values[i]
        local_layer_height = layer_height - delta_z

        # Clamp to avoid zero/negative or excessively high flow
        local_layer_height = max(local_layer_height, layer_height * 0.1)
        local_layer_height = min(local_layer_height, layer_height * 2.0)

        flow_factor = local_layer_height / layer_height
        e_sub = e_total * fraction * flow_factor

        move = GCodeMove(
            command="G1",
            x=points[i, 0],
            y=points[i, 1],
            z=z_values[i],
            e=e_sub,
        )

        # Include feedrate on first sub-move only
        if i == 1 and feedrate is not None:
            move.f = feedrate

        moves.append(move)

        # Record in collision checker
        if collision_checker is not None:
            collision_checker.add_extrusion(points[i, 0], points[i, 1], z_values[i])

    # Merge consecutive sub-moves with identical Z (within tolerance)
    return _merge_same_z(moves)


def _merge_same_z(moves: list[GCodeMove], z_tol: float = 0.001) -> list[GCodeMove]:
    """Merge consecutive moves that have the same Z to reduce G-code bloat."""
    if len(moves) <= 1:
        return moves

    merged: list[GCodeMove] = [moves[0]]
    for move in moves[1:]:
        prev = merged[-1]
        if (
            prev.z is not None
            and move.z is not None
            and abs(prev.z - move.z) < z_tol
        ):
            # Merge: update endpoint and accumulate E
            prev.x = move.x
            prev.y = move.y
            if prev.e is not None and move.e is not None:
                prev.e += move.e
        else:
            merged.append(move)

    return merged


def apply_zaa(
    gcode_list: list[str],
    caster: RayCaster,
    layer_height: float,
    max_contour: float,
    resolution: float,
    target_types: set[str],
    collision_checker: CollisionChecker | None = None,
) -> None:
    """Apply Z Anti-Aliasing to a Cura gcode_list in-place.

    Args:
        gcode_list: Cura's list of G-code chunk strings (modified in-place).
        caster: RayCaster with the scene mesh loaded.
        layer_height: Nominal layer height (mm).
        max_contour: Maximum Z contour depth below nominal (mm).
        resolution: Subdivision spacing (mm).
        target_types: Set of ;TYPE: strings to process (e.g. {"TOP-SURFACE-SKIN"}).
        collision_checker: Optional CollisionChecker instance.
    """
    state = GCodeState()
    prev_layer = -1

    for chunk_idx in range(len(gcode_list)):
        chunk = gcode_list[chunk_idx]
        lines = chunk.split("\n")
        new_lines: list[str] = []
        modified = False
        pending_reset_z: float | None = None  # deferred ZAA_RESET

        for line in lines:
            stripped = line.strip()

            # Save pre-move state before update
            prev_x, prev_y, prev_e = state.x, state.y, state.e

            # Detect type and layer changes
            type_change = state.update(stripped)

            # Reset collision checker on new layer
            if (
                collision_checker is not None
                and state.layer_number != prev_layer
                and state.layer_number >= 0
            ):
                collision_checker.reset_layer()
                prev_layer = state.layer_number

            # Check if this is an extrusion move in a target region
            parsed = parse_line(stripped)
            is_target_move = (
                isinstance(parsed, GCodeMove)
                and parsed.command == "G1"
                and parsed.e is not None
                and parsed.e > 0
                and state.current_type in target_types
                and state.nominal_z > 0
                and state.layer_number > 0  # skip first layer (bed adhesion)
            )

            if is_target_move:
                # Use pre-move position as start, post-move as end
                start_x = prev_x
                start_y = prev_y
                move_x = parsed.x if parsed.x is not None else prev_x
                move_y = parsed.y if parsed.y is not None else prev_y

                # Skip near-zero-length moves (still in target region, no reset)
                dist = math.hypot(move_x - start_x, move_y - start_y)
                if dist < 0.01:
                    new_lines.append(line)
                    continue

                # Compute E increment (relative amount for this segment)
                if state.relative_extrusion:
                    e_increment = parsed.e
                else:
                    e_increment = parsed.e - prev_e

                contoured = compute_contoured_moves(
                    x0=start_x,
                    y0=start_y,
                    x1=move_x,
                    y1=move_y,
                    e_total=e_increment,
                    nominal_z=state.nominal_z,
                    layer_height=layer_height,
                    max_contour=max_contour,
                    resolution=resolution,
                    caster=caster,
                    collision_checker=collision_checker,
                    feedrate=parsed.f,
                )

                # Check if contouring actually changed anything
                any_contour = any(
                    m.z is not None and abs(m.z - state.nominal_z) > 0.001
                    for m in contoured
                )

                if any_contour:
                    # Drop pending reset — we're continuing contoured moves
                    pending_reset_z = None

                    # Convert relative E values back to absolute if needed
                    if not state.relative_extrusion:
                        e_accum = prev_e
                        for m in contoured:
                            if m.e is not None:
                                e_accum += m.e
                                m.e = e_accum

                    for m in contoured:
                        new_lines.append(format_move(m))
                    # Defer the Z reset
                    pending_reset_z = state.nominal_z
                    modified = True
                else:
                    # Target region but this segment didn't contour.
                    # If we have a pending reset, this segment will extrude
                    # at the wrong Z (no Z in original line). Must reset.
                    if pending_reset_z is not None:
                        new_lines.append(
                            f"G1 Z{pending_reset_z:.4f} ;ZAA_RESET"
                        )
                        pending_reset_z = None
                        modified = True
                    new_lines.append(line)
            else:
                # Non-target line: check if we need to reset Z
                if pending_reset_z is not None:
                    # Only reset Z before moves that don't set their own Z,
                    # and skip reset before travels (G0) which are safe at any Z
                    next_parsed = parse_line(stripped)
                    is_travel = (
                        isinstance(next_parsed, GCodeMove)
                        and next_parsed.command == "G0"
                    )
                    has_z = (
                        isinstance(next_parsed, GCodeMove)
                        and next_parsed.z is not None
                    )
                    is_extrusion_without_z = (
                        isinstance(next_parsed, GCodeMove)
                        and next_parsed.command == "G1"
                        and next_parsed.e is not None
                        and next_parsed.z is None
                    )

                    if is_extrusion_without_z:
                        # Extruding at wrong Z — must reset
                        new_lines.append(
                            f"G1 Z{pending_reset_z:.4f} ;ZAA_RESET"
                        )
                    # For travels, Z moves, type changes, etc — no reset needed

                    pending_reset_z = None
                new_lines.append(line)

        # End of chunk: only reset if there's pending and last line matters
        pending_reset_z = None

        if modified:
            gcode_list[chunk_idx] = "\n".join(new_lines)
