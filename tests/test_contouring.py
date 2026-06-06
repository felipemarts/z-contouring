"""Tests for contouring module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math

import numpy as np
import pytest

from ZAAPlugin.core.contouring import (
    apply_zaa,
    compute_contoured_moves,
    subdivide_segment,
)
from ZAAPlugin.core.ray_caster import RayCaster


def _make_flat_surface(z: float = 10.0, extent: float = 100.0):
    """Large flat surface for testing."""
    vertices = np.array(
        [
            [0.0, 0.0, z],
            [extent, 0.0, z],
            [0.0, extent, z],
            [extent, extent, z],
        ],
        dtype=np.float64,
    )
    indices = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    return RayCaster(vertices, indices, cell_size=10.0)


def _make_sloped_surface():
    """Surface that slopes: z = 10 - 0.2*x, for x=[0,50], y=[0,50]."""
    vertices = np.array(
        [
            [0.0, 0.0, 10.0],
            [50.0, 0.0, 0.0],
            [0.0, 50.0, 10.0],
            [50.0, 50.0, 0.0],
        ],
        dtype=np.float64,
    )
    indices = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    return RayCaster(vertices, indices, cell_size=10.0)


class TestSubdivideSegment:
    def test_short_segment(self):
        points = subdivide_segment(0, 0, 0.3, 0, resolution=0.5)
        assert len(points) == 2  # start + end only
        assert abs(points[0, 0] - 0.0) < 1e-10
        assert abs(points[-1, 0] - 0.3) < 1e-10

    def test_long_segment(self):
        points = subdivide_segment(0, 0, 5, 0, resolution=1.0)
        assert len(points) == 6  # 0, 1, 2, 3, 4, 5
        for i in range(len(points)):
            assert abs(points[i, 0] - i) < 1e-10

    def test_diagonal(self):
        points = subdivide_segment(0, 0, 3, 4, resolution=1.0)
        # Length = 5, so 5 segments, 6 points
        assert len(points) == 6
        assert abs(points[-1, 0] - 3.0) < 1e-10
        assert abs(points[-1, 1] - 4.0) < 1e-10

    def test_endpoints_exact(self):
        points = subdivide_segment(1.5, 2.5, 7.3, 9.1, resolution=0.5)
        assert abs(points[0, 0] - 1.5) < 1e-10
        assert abs(points[0, 1] - 2.5) < 1e-10
        assert abs(points[-1, 0] - 7.3) < 1e-10
        assert abs(points[-1, 1] - 9.1) < 1e-10


class TestComputeContouredMoves:
    def test_flat_surface_no_contour(self):
        """On a flat surface at nominal_z, no contouring should occur."""
        caster = _make_flat_surface(z=10.0)
        moves = compute_contoured_moves(
            x0=5.0, y0=5.0, x1=15.0, y1=5.0,
            e_total=1.0,
            nominal_z=10.0,
            layer_height=0.2,
            max_contour=0.1,
            resolution=1.0,
            caster=caster,
        )
        # Surface is at nominal_z, so Z should be == nominal_z everywhere
        for m in moves:
            assert m.z is not None
            assert abs(m.z - 10.0) < 0.002

    def test_sloped_surface_contours(self):
        """On a sloped surface, Z should vary along the segment."""
        caster = _make_sloped_surface()
        moves = compute_contoured_moves(
            x0=5.0, y0=25.0, x1=20.0, y1=25.0,
            e_total=1.0,
            nominal_z=10.0,
            layer_height=0.2,
            max_contour=0.1,
            resolution=1.0,
            caster=caster,
        )
        # The surface drops as x increases, so some Z values should be < 10.0
        z_values = [m.z for m in moves if m.z is not None]
        assert any(z < 10.0 - 0.001 for z in z_values)

    def test_e_conservation_flat(self):
        """On a flat surface (no Z change), total E should equal original."""
        caster = _make_flat_surface(z=10.0)
        moves = compute_contoured_moves(
            x0=10.0, y0=10.0, x1=20.0, y1=10.0,
            e_total=1.0,
            nominal_z=10.0,
            layer_height=0.2,
            max_contour=0.1,
            resolution=1.0,
            caster=caster,
        )
        total_e = sum(m.e for m in moves if m.e is not None)
        assert abs(total_e - 1.0) < 0.01

    def test_flow_reduces_when_z_drops(self):
        """When Z drops, local layer height decreases, so total E should be less."""
        caster = _make_sloped_surface()
        moves = compute_contoured_moves(
            x0=5.0, y0=25.0, x1=20.0, y1=25.0,
            e_total=1.0,
            nominal_z=10.0,
            layer_height=0.2,
            max_contour=0.1,
            resolution=1.0,
            caster=caster,
        )
        total_e = sum(m.e for m in moves if m.e is not None)
        # Z drops below nominal, so flow should be reduced
        assert total_e < 1.0

    def test_feedrate_on_first_only(self):
        """Feedrate should appear only on the first sub-move."""
        caster = _make_flat_surface(z=10.0)
        moves = compute_contoured_moves(
            x0=5.0, y0=5.0, x1=15.0, y1=5.0,
            e_total=1.0,
            nominal_z=10.0,
            layer_height=0.2,
            max_contour=0.1,
            resolution=1.0,
            caster=caster,
            feedrate=1200.0,
        )
        if len(moves) > 1:
            assert moves[0].f == 1200.0
            for m in moves[1:]:
                assert m.f is None

    def test_max_contour_clamp(self):
        """Z should never drop below nominal_z - max_contour."""
        caster = _make_sloped_surface()
        max_contour = 0.05
        moves = compute_contoured_moves(
            x0=10.0, y0=25.0, x1=30.0, y1=25.0,
            e_total=1.0,
            nominal_z=10.0,
            layer_height=0.2,
            max_contour=max_contour,
            resolution=1.0,
            caster=caster,
        )
        for m in moves:
            if m.z is not None:
                assert m.z >= 10.0 - max_contour - 0.001


class TestApplyZAA:
    def test_processes_top_surface_skin(self):
        """apply_zaa should modify TOP-SURFACE-SKIN extrusion moves."""
        caster = _make_sloped_surface()
        gcode_list = [
            ";Generated by Cura\n",
            ";LAYER:10\n"
            "G0 Z10.0\n"
            ";TYPE:TOP-SURFACE-SKIN\n"
            "G1 X5.0 Y25.0 E0.1\n"
            "G1 X20.0 Y25.0 E1.0\n"
            ";TYPE:FILL\n"
            "G1 X30.0 Y25.0 E1.0\n",
        ]
        apply_zaa(
            gcode_list, caster,
            layer_height=0.2,
            max_contour=0.1,
            resolution=1.0,
            target_types={"TOP-SURFACE-SKIN"},
        )
        # The second chunk should have been modified (contains contoured moves)
        assert "ZAA_RESET" in gcode_list[1]

    def test_does_not_modify_fill(self):
        """apply_zaa should NOT modify FILL regions."""
        caster = _make_flat_surface(z=10.0)
        gcode_list = [
            ";Generated by Cura\n",
            ";LAYER:10\n"
            "G0 Z10.0\n"
            ";TYPE:FILL\n"
            "G1 X10.0 Y10.0 E0.5\n"
            "G1 X20.0 Y10.0 E1.0\n",
        ]
        original = gcode_list[1]
        apply_zaa(
            gcode_list, caster,
            layer_height=0.2,
            max_contour=0.1,
            resolution=1.0,
            target_types={"TOP-SURFACE-SKIN"},
        )
        assert gcode_list[1] == original
