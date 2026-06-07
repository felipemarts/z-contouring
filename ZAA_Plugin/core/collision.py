"""Nozzle collision detection for Z Anti-Aliasing.

Prevents the nozzle from descending into previously deposited material
by tracking extrusion positions and checking clearance before lowering Z.

Pure Python/numpy — no Cura dependencies.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np


class CollisionChecker:
    """Spatial-hash-based collision checker for nozzle clearance.

    Models the nozzle tip as a circle of given diameter. Before lowering Z
    at any point, checks if deposited material within the nozzle radius
    would cause a collision.
    """

    def __init__(self, nozzle_diameter: float = 0.4, cell_size: float = 1.0) -> None:
        """Initialize the collision checker.

        Args:
            nozzle_diameter: Nozzle tip diameter (mm).
            cell_size: Spatial hash cell size (mm). Should be >= nozzle_diameter.
        """
        self.nozzle_radius = nozzle_diameter / 2.0
        self.nozzle_radius_sq = self.nozzle_radius ** 2
        self.cell_size = max(cell_size, nozzle_diameter)
        self._grid: dict[tuple[int, int], list[tuple[float, float, float]]] = (
            defaultdict(list)
        )

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        """Convert world coords to grid cell."""
        return (
            int(np.floor(x / self.cell_size)),
            int(np.floor(y / self.cell_size)),
        )

    def add_extrusion(self, x: float, y: float, z: float) -> None:
        """Record a deposited extrusion point."""
        cell = self._cell(x, y)
        self._grid[cell].append((x, y, z))

    def check_safe_z(self, x: float, y: float, proposed_z: float) -> float:
        """Check if the nozzle can safely descend to proposed_z at (x, y).

        Returns the safe Z: either proposed_z if clear, or a higher Z if
        neighboring deposited material would cause a collision.
        """
        cx, cy = self._cell(x, y)
        max_neighbor_z = -float("inf")

        # Check the cell and all 8 neighbors
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                cell = (cx + dx, cy + dy)
                for (px, py, pz) in self._grid.get(cell, []):
                    dist_sq = (x - px) ** 2 + (y - py) ** 2
                    if dist_sq <= self.nozzle_radius_sq:
                        if pz > max_neighbor_z:
                            max_neighbor_z = pz

        if max_neighbor_z > proposed_z:
            return max_neighbor_z
        return proposed_z

    def reset_layer(self) -> None:
        """Clear all deposited points for a new layer."""
        self._grid.clear()
