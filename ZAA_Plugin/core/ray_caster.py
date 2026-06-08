"""Vertical ray-caster with 2D grid acceleration.

Pure numpy implementation — no external dependencies beyond numpy.
Optimized for the ZAA use case: all rays are vertical (direction = (0, 0, -1)),
which simplifies the Möller-Trumbore intersection test significantly.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

_EPS = 1e-10


class RayCaster:
    """Casts vertical rays against a triangle mesh using a 2D XY grid."""

    def __init__(
        self, vertices: np.ndarray, indices: np.ndarray, cell_size: float = 2.0
    ) -> None:
        """Build the acceleration structure.

        Args:
            vertices: (N, 3) array of vertex positions (Z-up coordinate system).
            indices: (M, 3) array of triangle vertex indices.
            cell_size: Size of each grid cell in XY (mm).
        """
        self.vertices = np.asarray(vertices, dtype=np.float64)
        self.indices = np.asarray(indices, dtype=np.int64)
        self.cell_size = cell_size

        # Pre-extract triangle vertex arrays (M, 3) each
        self.v0 = self.vertices[self.indices[:, 0]]
        self.v1 = self.vertices[self.indices[:, 1]]
        self.v2 = self.vertices[self.indices[:, 2]]

        # Build 2D XY grid
        self._build_grid()

    def _build_grid(self) -> None:
        """Bucket triangles into a 2D grid based on their XY bounding boxes."""
        xy_min_all = self.vertices[:, :2].min(axis=0)
        xy_max_all = self.vertices[:, :2].max(axis=0)

        self._grid_origin = xy_min_all - self.cell_size  # small padding
        grid_extent = xy_max_all - self._grid_origin + self.cell_size
        self._grid_shape = np.ceil(grid_extent / self.cell_size).astype(int) + 1
        self._grid: dict[tuple[int, int], list[int]] = defaultdict(list)

        # Per-triangle XY bounding boxes
        tri_xy = np.stack(
            [self.v0[:, :2], self.v1[:, :2], self.v2[:, :2]], axis=1
        )  # (M, 3, 2)
        tri_xy_min = tri_xy.min(axis=1)  # (M, 2)
        tri_xy_max = tri_xy.max(axis=1)  # (M, 2)

        # Convert to grid cell ranges
        cell_min = np.floor(
            (tri_xy_min - self._grid_origin) / self.cell_size
        ).astype(int)
        cell_max = np.floor(
            (tri_xy_max - self._grid_origin) / self.cell_size
        ).astype(int)

        for tri_idx in range(len(self.indices)):
            for ix in range(cell_min[tri_idx, 0], cell_max[tri_idx, 0] + 1):
                for iy in range(cell_min[tri_idx, 1], cell_max[tri_idx, 1] + 1):
                    self._grid[(ix, iy)].append(tri_idx)

    def _xy_to_cell(self, x: float, y: float) -> tuple[int, int]:
        """Convert (x, y) world coords to grid cell indices."""
        ix = int(np.floor((x - self._grid_origin[0]) / self.cell_size))
        iy = int(np.floor((y - self._grid_origin[1]) / self.cell_size))
        return ix, iy

    def hit_z(self, x: float, y: float) -> tuple[float, float] | None:
        """Cast a vertical ray downward at (x, y) and return the highest Z hit.

        Returns (hit_z, normal_z) tuple, or None if no triangle is hit.
        normal_z is the Z component of the unit normal of the hit triangle
        (1.0 = flat horizontal top surface, 0.0 = vertical wall).
        """
        cell = self._xy_to_cell(x, y)
        candidates = self._grid.get(cell)
        if not candidates:
            return None

        candidate_indices = np.array(candidates, dtype=np.int64)
        return self._intersect_vertical(x, y, candidate_indices)

    def hit_z_batch(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Cast vertical rays for multiple (x, y) points.

        Args:
            points: (N, 2) array of (x, y) positions.

        Returns:
            Tuple of (z_values, normal_z_values), each (N,) arrays.
            NaN where no hit occurred.
        """
        z_result = np.full(len(points), np.nan, dtype=np.float64)
        nz_result = np.full(len(points), np.nan, dtype=np.float64)

        # Group points by grid cell for batched intersection
        cell_to_point_indices: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i, (x, y) in enumerate(points):
            cell = self._xy_to_cell(x, y)
            cell_to_point_indices[cell].append(i)

        for cell, point_indices in cell_to_point_indices.items():
            candidates = self._grid.get(cell)
            if not candidates:
                continue

            candidate_indices = np.array(candidates, dtype=np.int64)
            for pi in point_indices:
                hit = self._intersect_vertical(
                    points[pi, 0], points[pi, 1], candidate_indices
                )
                if hit is not None:
                    z_result[pi] = hit[0]
                    nz_result[pi] = hit[1]

        return z_result, nz_result

    def _intersect_vertical(
        self, x: float, y: float, tri_indices: np.ndarray
    ) -> tuple[float, float] | None:
        """Vectorized Möller-Trumbore for a vertical ray at (x, y).

        The ray goes from (x, y, +inf) downward in -Z direction.
        We simplify the general algorithm since direction = (0, 0, -1).

        Returns (hit_z, normal_z) or None.
        normal_z is the Z component of the unit normal of the hit triangle.
        """
        v0 = self.v0[tri_indices]  # (K, 3)
        v1 = self.v1[tri_indices]
        v2 = self.v2[tri_indices]

        e1 = v1 - v0  # (K, 3)
        e2 = v2 - v0  # (K, 3)

        # cross(direction, e2) where direction = (0, 0, -1)
        # = (0 * e2_z - (-1) * e2_y,  (-1) * e2_x - 0 * e2_z,  0 * e2_y - 0 * e2_x)
        # = (e2_y, -e2_x, 0)
        h = np.column_stack([e2[:, 1], -e2[:, 0], np.zeros(len(tri_indices))])

        # det = dot(e1, h)
        det = np.sum(e1 * h, axis=1)

        # Filter degenerate triangles
        valid = np.abs(det) > _EPS
        if not np.any(valid):
            return None

        inv_det = np.zeros_like(det)
        inv_det[valid] = 1.0 / det[valid]

        # s = ray_origin - v0
        # Ray origin: use z=0 as reference, actual z doesn't matter for
        # barycentric coords since ray is vertical.
        # We use a high Z origin and compute t to get actual hit Z.
        z_origin = float(v0[:, 2].max()) + 100.0
        s = np.empty_like(v0)
        s[:, 0] = x - v0[:, 0]
        s[:, 1] = y - v0[:, 1]
        s[:, 2] = z_origin - v0[:, 2]

        # u = dot(s, h) * inv_det
        u = np.sum(s * h, axis=1) * inv_det

        # cross(s, e1)
        q = np.cross(s, e1)

        # v = dot(direction, q) * inv_det
        # direction = (0, 0, -1), so dot = -q_z
        v = -q[:, 2] * inv_det

        # t = dot(e2, q) * inv_det
        t = np.sum(e2 * q, axis=1) * inv_det

        # Valid hit: u in [0,1], v in [0,1], u+v <= 1, t > 0
        hit_mask = valid & (u >= -_EPS) & (v >= -_EPS) & (u + v <= 1.0 + _EPS) & (t > 0)

        if not np.any(hit_mask):
            return None

        # Z of hit point = z_origin - t (since ray goes in -Z)
        hit_z_values = z_origin - t[hit_mask]

        # Compute surface normals for hit triangles: cross(e1, e2)
        hit_e1 = e1[hit_mask]
        hit_e2 = e2[hit_mask]
        normals = np.cross(hit_e1, hit_e2)  # (H, 3)
        norms = np.linalg.norm(normals, axis=1)
        norms[norms < _EPS] = 1.0  # avoid div-by-zero for degenerate
        normal_z = normals[:, 2] / norms  # normalized Z component

        # Find the highest Z hit (closest to ray origin)
        best_idx = int(np.argmax(hit_z_values))
        return float(hit_z_values[best_idx]), float(normal_z[best_idx])
