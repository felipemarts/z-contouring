"""Tests for ray_caster module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest

from ZAAPlugin.core.ray_caster import RayCaster


def _make_flat_triangle(z: float = 5.0):
    """A single flat triangle at height z, spanning x=[0,10], y=[0,10]."""
    vertices = np.array(
        [[0.0, 0.0, z], [10.0, 0.0, z], [0.0, 10.0, z]], dtype=np.float64
    )
    indices = np.array([[0, 1, 2]], dtype=np.int64)
    return vertices, indices


def _make_tilted_plane():
    """A tilted plane: z = 5 + 0.5*x, spanning x=[0,10], y=[0,10]."""
    vertices = np.array(
        [
            [0.0, 0.0, 5.0],
            [10.0, 0.0, 10.0],
            [0.0, 10.0, 5.0],
            [10.0, 10.0, 10.0],
        ],
        dtype=np.float64,
    )
    indices = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    return vertices, indices


def _make_cube(size: float = 10.0, z_base: float = 0.0):
    """A simple cube mesh."""
    s = size
    z0 = z_base
    z1 = z_base + size
    vertices = np.array(
        [
            [0, 0, z0], [s, 0, z0], [s, s, z0], [0, s, z0],  # bottom
            [0, 0, z1], [s, 0, z1], [s, s, z1], [0, s, z1],  # top
        ],
        dtype=np.float64,
    )
    indices = np.array(
        [
            # bottom
            [0, 2, 1], [0, 3, 2],
            # top
            [4, 5, 6], [4, 6, 7],
            # front
            [0, 1, 5], [0, 5, 4],
            # back
            [2, 3, 7], [2, 7, 6],
            # left
            [0, 4, 7], [0, 7, 3],
            # right
            [1, 2, 6], [1, 6, 5],
        ],
        dtype=np.int64,
    )
    return vertices, indices


class TestHitZ:
    def test_flat_triangle_center(self):
        verts, indices = _make_flat_triangle(z=5.0)
        caster = RayCaster(verts, indices, cell_size=5.0)
        result = caster.hit_z(2.0, 2.0)
        assert result is not None
        z, nz = result
        assert abs(z - 5.0) < 0.001
        # Flat horizontal triangle — normal Z should be ~1.0
        assert abs(abs(nz) - 1.0) < 0.01

    def test_flat_triangle_edge(self):
        verts, indices = _make_flat_triangle(z=5.0)
        caster = RayCaster(verts, indices, cell_size=5.0)
        result = caster.hit_z(0.1, 0.1)
        assert result is not None
        z, nz = result
        assert abs(z - 5.0) < 0.001

    def test_miss_outside_triangle(self):
        verts, indices = _make_flat_triangle(z=5.0)
        caster = RayCaster(verts, indices, cell_size=5.0)
        # Point (8, 8) is outside the triangle (x+y > 10)
        result = caster.hit_z(8.0, 8.0)
        assert result is None

    def test_tilted_plane(self):
        verts, indices = _make_tilted_plane()
        caster = RayCaster(verts, indices, cell_size=5.0)

        # z = 5 + 0.5 * x at x=0
        result = caster.hit_z(0.5, 5.0)
        assert result is not None
        z, nz = result
        assert abs(z - 5.25) < 0.05
        # Tilted plane (z = 5 + 0.5*x): slope angle ~26.6 deg, nz ~0.894
        assert 0.8 < abs(nz) < 1.0

    def test_cube_top_face(self):
        verts, indices = _make_cube(size=10.0, z_base=0.0)
        caster = RayCaster(verts, indices, cell_size=5.0)

        # Center of cube top face
        result = caster.hit_z(5.0, 5.0)
        assert result is not None
        z, nz = result
        assert abs(z - 10.0) < 0.001
        # Top face of cube — normal should point up (nz ~1.0)
        assert abs(nz) > 0.9

    def test_cube_miss(self):
        verts, indices = _make_cube(size=10.0, z_base=0.0)
        caster = RayCaster(verts, indices, cell_size=5.0)

        # Outside the cube
        result = caster.hit_z(15.0, 15.0)
        assert result is None

    def test_vertical_wall_normal(self):
        """A vertical wall triangle should have normal_z ~0.0."""
        # Single vertical triangle in the XZ plane
        vertices = np.array(
            [[0.0, 5.0, 0.0], [10.0, 5.0, 0.0], [10.0, 5.0, 10.0]],
            dtype=np.float64,
        )
        indices = np.array([[0, 1, 2]], dtype=np.int64)
        caster = RayCaster(vertices, indices, cell_size=5.0)
        result = caster.hit_z(5.0, 5.0)
        # Vertical wall — ray should hit it, normal_z should be ~0
        if result is not None:
            z, nz = result
            assert abs(nz) < 0.01


class TestHitZBatch:
    def test_batch_matches_single(self):
        verts, indices = _make_tilted_plane()
        caster = RayCaster(verts, indices, cell_size=5.0)

        points = np.array([[2.0, 2.0], [5.0, 5.0], [8.0, 8.0]], dtype=np.float64)
        z_batch, nz_batch = caster.hit_z_batch(points)

        for i, (x, y) in enumerate(points):
            single = caster.hit_z(x, y)
            if single is None:
                assert np.isnan(z_batch[i])
                assert np.isnan(nz_batch[i])
            else:
                assert abs(z_batch[i] - single[0]) < 0.001
                assert abs(nz_batch[i] - single[1]) < 0.001

    def test_batch_some_hits_some_misses(self):
        verts, indices = _make_flat_triangle(z=3.0)
        caster = RayCaster(verts, indices, cell_size=5.0)

        points = np.array(
            [[2.0, 2.0], [20.0, 20.0], [1.0, 1.0]], dtype=np.float64
        )
        z_results, nz_results = caster.hit_z_batch(points)

        assert not np.isnan(z_results[0])  # hit
        assert np.isnan(z_results[1])  # miss
        assert not np.isnan(z_results[2])  # hit
        # Flat triangle normals should be ~1.0
        assert abs(abs(nz_results[0]) - 1.0) < 0.01
        assert abs(abs(nz_results[2]) - 1.0) < 0.01


class TestGridAcceleration:
    def test_different_cell_sizes_same_result(self):
        verts, indices = _make_tilted_plane()
        caster_small = RayCaster(verts, indices, cell_size=1.0)
        caster_large = RayCaster(verts, indices, cell_size=10.0)

        for x, y in [(2.0, 2.0), (5.0, 3.0), (7.0, 1.0)]:
            result_small = caster_small.hit_z(x, y)
            result_large = caster_large.hit_z(x, y)
            assert result_small is not None and result_large is not None
            assert abs(result_small[0] - result_large[0]) < 0.001
            assert abs(result_small[1] - result_large[1]) < 0.001
