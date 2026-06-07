"""Tests for gcode_parser module."""

import sys
import os

# Add parent directory to path so we can import the plugin modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ZAAPlugin.core.gcode_parser import (
    GCodeMove,
    GCodeState,
    format_move,
    iterate_gcode,
    parse_line,
)


class TestParseLine:
    def test_parse_g1_full(self):
        result = parse_line("G1 X10.5 Y20.3 Z1.2 E0.5 F1200")
        assert isinstance(result, GCodeMove)
        assert result.command == "G1"
        assert result.x == 10.5
        assert result.y == 20.3
        assert result.z == 1.2
        assert result.e == 0.5
        assert result.f == 1200.0

    def test_parse_g0(self):
        result = parse_line("G0 X50 Y50")
        assert isinstance(result, GCodeMove)
        assert result.command == "G0"
        assert result.x == 50.0
        assert result.y == 50.0
        assert result.z is None
        assert result.e is None

    def test_parse_g1_partial(self):
        result = parse_line("G1 E-0.8")
        assert isinstance(result, GCodeMove)
        assert result.e == -0.8
        assert result.x is None

    def test_parse_with_comment(self):
        result = parse_line("G1 X10 Y20 E0.5 ;TYPE:WALL-OUTER")
        assert isinstance(result, GCodeMove)
        assert result.x == 10.0
        assert result.comment == ";TYPE:WALL-OUTER"

    def test_parse_comment_only(self):
        result = parse_line(";TYPE:TOP-SURFACE-SKIN")
        assert isinstance(result, str)
        assert result == ";TYPE:TOP-SURFACE-SKIN"

    def test_parse_mcode(self):
        result = parse_line("M82")
        assert isinstance(result, str)

    def test_parse_empty(self):
        result = parse_line("")
        assert isinstance(result, str)

    def test_parse_negative_coords(self):
        result = parse_line("G1 X-5.0 Y-10.0")
        assert isinstance(result, GCodeMove)
        assert result.x == -5.0
        assert result.y == -10.0


class TestFormatMove:
    def test_format_full(self):
        move = GCodeMove(command="G1", x=10.0, y=20.0, z=1.2, e=0.5, f=1200)
        result = format_move(move)
        assert "G1" in result
        assert "X10.0000" in result
        assert "Y20.0000" in result
        assert "Z1.2000" in result
        assert "E0.50000" in result
        assert "F1200" in result

    def test_format_partial(self):
        move = GCodeMove(command="G1", x=10.0, y=20.0, e=0.5)
        result = format_move(move)
        assert "Z" not in result
        assert "F" not in result

    def test_format_with_comment(self):
        move = GCodeMove(command="G1", x=10.0, comment=";test")
        result = format_move(move)
        assert result.endswith(";test")

    def test_roundtrip(self):
        original = "G1 X10.0000 Y20.0000 Z1.2000 E0.50000"
        parsed = parse_line(original)
        assert isinstance(parsed, GCodeMove)
        formatted = format_move(parsed)
        # Re-parse and compare values
        reparsed = parse_line(formatted)
        assert isinstance(reparsed, GCodeMove)
        assert abs(reparsed.x - parsed.x) < 0.0001
        assert abs(reparsed.y - parsed.y) < 0.0001
        assert abs(reparsed.z - parsed.z) < 0.0001
        assert abs(reparsed.e - parsed.e) < 0.00001


class TestGCodeState:
    def test_type_detection(self):
        state = GCodeState()
        result = state.update(";TYPE:TOP-SURFACE-SKIN")
        assert result == "TOP-SURFACE-SKIN"
        assert state.current_type == "TOP-SURFACE-SKIN"

    def test_layer_detection(self):
        state = GCodeState()
        state.update(";LAYER:5")
        assert state.layer_number == 5

    def test_position_tracking(self):
        state = GCodeState()
        state.update("G1 X10 Y20 Z0.3 E1.0")
        assert state.x == 10.0
        assert state.y == 20.0
        assert state.z == 0.3
        assert state.e == 1.0

    def test_nominal_z_set_after_layer_marker(self):
        state = GCodeState()
        state.update(";LAYER:0")
        state.update("G0 F3600 X50 Y50 Z0.3")
        assert state.nominal_z == 0.3
        assert state.z == 0.3

    def test_nominal_z_from_layer_with_xyz_move(self):
        state = GCodeState()
        state.update(";LAYER:0")
        state.update("G0 X10 Y20 Z0.6")
        # First Z after LAYER marker sets nominal_z even with XY
        assert state.nominal_z == 0.6

    def test_nominal_z_not_updated_without_layer_marker(self):
        state = GCodeState()
        state.update(";LAYER:0")
        state.update("G0 Z0.6")
        assert state.nominal_z == 0.6
        state.update("G1 X10 Y20 Z0.7 E0.5")
        # No new LAYER marker — nominal_z should stay at 0.6
        assert state.nominal_z == 0.6
        assert state.z == 0.7

    def test_nominal_z_updates_on_new_layer(self):
        state = GCodeState()
        state.update(";LAYER:0")
        state.update("G0 Z0.3")
        assert state.nominal_z == 0.3
        state.update(";LAYER:1")
        state.update("G0 X50 Y50 Z0.6")
        assert state.nominal_z == 0.6

    def test_extrusion_mode_absolute(self):
        state = GCodeState()
        state.update("M82")
        assert not state.relative_extrusion
        state.update("G1 E5.0")
        assert state.e == 5.0
        state.update("G1 E7.0")
        assert state.e == 7.0

    def test_extrusion_mode_relative(self):
        state = GCodeState()
        state.update("M83")
        assert state.relative_extrusion
        state.update("G1 E1.0")
        assert state.e == 1.0
        state.update("G1 E1.0")
        assert state.e == 2.0

    def test_feedrate_tracking(self):
        state = GCodeState()
        state.update("G1 X10 Y10 F1200")
        assert state.f == 1200.0


class TestIterateGcode:
    def test_basic(self):
        gcode_list = [
            ";Start\nG28\n",
            "G1 X10 Y10 E0.5\nG1 X20 Y20 E1.0\n",
        ]
        items = list(iterate_gcode(gcode_list))
        assert len(items) > 0
        # First chunk
        assert items[0] == (0, 0, ";Start")
        assert items[1] == (0, 1, "G28")
        # Second chunk
        chunk1_items = [(c, l, s) for c, l, s in items if c == 1]
        assert any("X10" in s for _, _, s in chunk1_items)
