"""Tests for collision module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ZAAPlugin.core.collision import CollisionChecker


class TestCollisionChecker:
    def test_no_deposits_returns_proposed(self):
        checker = CollisionChecker(nozzle_diameter=0.4)
        z = checker.check_safe_z(5.0, 5.0, 3.0)
        assert z == 3.0

    def test_clamps_when_neighbor_higher(self):
        checker = CollisionChecker(nozzle_diameter=0.4)
        # Deposit material at (5.0, 5.0, 5.0)
        checker.add_extrusion(5.0, 5.0, 5.0)
        # Try to descend to 3.0 at a point within nozzle radius
        z = checker.check_safe_z(5.1, 5.0, 3.0)
        assert z == 5.0  # clamped to neighbor height

    def test_no_clamp_when_far_away(self):
        checker = CollisionChecker(nozzle_diameter=0.4)
        checker.add_extrusion(5.0, 5.0, 5.0)
        # Point far from the deposit (beyond nozzle radius)
        z = checker.check_safe_z(10.0, 10.0, 3.0)
        assert z == 3.0

    def test_no_clamp_when_proposed_higher(self):
        checker = CollisionChecker(nozzle_diameter=0.4)
        checker.add_extrusion(5.0, 5.0, 3.0)
        # Proposed Z is higher than deposit
        z = checker.check_safe_z(5.1, 5.0, 5.0)
        assert z == 5.0

    def test_reset_layer_clears(self):
        checker = CollisionChecker(nozzle_diameter=0.4)
        checker.add_extrusion(5.0, 5.0, 5.0)
        checker.reset_layer()
        # After reset, no deposits to collide with
        z = checker.check_safe_z(5.1, 5.0, 3.0)
        assert z == 3.0

    def test_multiple_deposits_uses_highest(self):
        checker = CollisionChecker(nozzle_diameter=0.8)
        checker.add_extrusion(5.0, 5.0, 3.0)
        checker.add_extrusion(5.1, 5.0, 7.0)
        checker.add_extrusion(5.2, 5.0, 5.0)
        # Should clamp to the highest neighbor (7.0)
        z = checker.check_safe_z(5.15, 5.0, 2.0)
        assert z == 7.0
