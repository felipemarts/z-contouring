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
        z = caster.hit_z(2.0, 2.0)
        assert z is not None
        assert abs(z - 5.0) < 0.001

    def test_flat_triangle_edge(self):
        verts, indices = _make_flat_triangle(z=5.0)
        caster = RayCaster(verts, indices, cell_size=5.0)
        z = caster.hit_z(0.1, 0.1)
        assert z is not None
        assert abs(z - 5.0) < 0.001

    def test_miss_outside_triangle(self):
        verts, indices = _make_flat_triangle(z=5.0)
        caster = RayCaster(verts, indices, cell_size=5.0)
        # Point (8, 8) is outside the triangle (x+y > 10)
        z = caster.hit_z(8.0, 8.0)
        assert z is None

    def test_tilted_plane(self):
        verts, indices = _make_tilted_plane()
        caster = RayCaster(verts, indices, cell_size=5.0)

        # z = 5 + 0.5 * x at x=0
        z = caster.hit_z(0.5, 5.0)
        assert z is not None
        assert abs(z - 5.25) < 0.05

        # z = 5 + 0.5 * x at x=6
        z = caster.hit_z(6.0, 3.0)
        assert z is not None
        assert abs(z - 8.0) < 0.05

    def test_cube_top_face(self):
        verts, indices = _make_cube(size=10.0, z_base=0.0)
        caster = RayCaster(verts, indices, cell_size=5.0)

        # Center of cube top face
        z = caster.hit_z(5.0, 5.0)
        assert z is not None
        assert abs(z - 10.0) < 0.001

    def test_cube_miss(self):
        verts, indices = _make_cube(size=10.0, z_base=0.0)
        caster = RayCaster(verts, indices, cell_size=5.0)

        # Outside the cube
        z = caster.hit_z(15.0, 15.0)
        assert z is None


class TestHitZBatch:
    def test_batch_matches_single(self):
        verts, indices = _make_tilted_plane()
        caster = RayCaster(verts, indices, cell_size=5.0)

        points = np.array([[2.0, 2.0], [5.0, 5.0], [8.0, 8.0]], dtype=np.float64)
        batch_results = caster.hit_z_batch(points)

        for i, (x, y) in enumerate(points):
            single = caster.hit_z(x, y)
            if single is None:
                assert np.isnan(batch_results[i])
            else:
                assert abs(batch_results[i] - single) < 0.001

    def test_batch_some_hits_some_misses(self):
        verts, indices = _make_flat_triangle(z=3.0)
        caster = RayCaster(verts, indices, cell_size=5.0)

        points = np.array(
            [[2.0, 2.0], [20.0, 20.0], [1.0, 1.0]], dtype=np.float64
        )
        results = caster.hit_z_batch(points)

        assert not np.isnan(results[0])  # hit
        assert np.isnan(results[1])  # miss
        assert not np.isnan(results[2])  # hit


class TestGridAcceleration:
    def test_different_cell_sizes_same_result(self):
        verts, indices = _make_tilted_plane()
        caster_small = RayCaster(verts, indices, cell_size=1.0)
        caster_large = RayCaster(verts, indices, cell_size=10.0)

        for x, y in [(2.0, 2.0), (5.0, 3.0), (7.0, 1.0)]:
            z_small = caster_small.hit_z(x, y)
            z_large = caster_large.hit_z(x, y)
            assert z_small is not None and z_large is not None
            assert abs(z_small - z_large) < 0.001
