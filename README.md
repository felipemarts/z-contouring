# Z Anti-Aliasing (ZAA) Plugin for Cura

A Cura 5.x Extension plugin that reduces stair-stepping on curved top surfaces by varying the Z height within a layer to follow the actual mesh surface.

Unlike external tools that require manual STL export, this plugin accesses the 3D mesh directly from Cura's scene -- no extra steps needed.

## How It Works

1. After slicing, the plugin intercepts the G-code before it is saved/sent
2. For each extrusion move in target regions (SKIN, WALL-OUTER, TOP-SURFACE-SKIN), the segment is subdivided into fine sub-points
3. A vertical ray is cast at each sub-point against the original mesh to find the true surface Z
4. The Z is adjusted to follow the surface, with smoothing across the full segment length to eliminate stair-stepping
5. Extrusion (E) values are adjusted to compensate for the varying local layer height (flow ratio clamped to 0.5x-1.5x)
6. A collision checker prevents the nozzle from descending into previously deposited material

```
; Before (flat layer -- stair-stepping)
G1 X10.0 Y10.0 E0.5

; After (contoured -- smooth surface)
G1 X10.2 Y10.0 Z2.97 E0.048
G1 X10.4 Y10.0 Z2.95 E0.047
G1 X10.6 Y10.0 Z2.94 E0.046
```

## Installation

### From GitHub Release

1. Download the latest `ZAAPlugin.zip` from [Releases](../../releases)
2. Extract into your Cura plugins directory:
   - **Windows:** `%APPDATA%\cura\5.x\plugins\`
   - **macOS:** `~/Library/Application Support/cura/5.x/plugins/`
   - **Linux:** `~/.local/share/cura/5.x/plugins/`
3. Restart Cura

### From Source

Clone this repo and copy/symlink the `ZAAPlugin/` folder into your Cura plugins directory.

The plugin appears under **Extensions > Z Anti-Aliasing**.

## Settings

Access via **Extensions > Z Anti-Aliasing > Settings...**

| Setting | Default | Description |
|---------|---------|-------------|
| **Enabled** | On | Enable/disable ZAA processing |
| **Resolution** | 0.5 mm | Subdivision spacing along extrusion segments |
| **Target regions** | SKIN, WALL-OUTER, TOP-SURFACE-SKIN | G-code region types to process |
| **Collision detection** | On | Prevent nozzle crashes with deposited material |

The contour depth is automatically set to match the layer height -- each layer can follow the full surface transition to the layer below.

## Architecture

```
ZAAPlugin/
  __init__.py          # Plugin entry point (deferred Cura imports)
  plugin.json          # Cura plugin metadata (API 8)
  ZAAExtension.py      # Extension class: menu, preferences, orchestration
  core/
    gcode_parser.py    # G-code parsing, formatting, state tracking
    ray_caster.py      # Vertical ray-mesh intersection with 2D grid acceleration
    contouring.py      # Subdivision, Z replacement, flow compensation, smoothing
    collision.py       # Spatial-hash nozzle collision checker
    mesh_access.py     # Extract meshes from Cura scene (Y-up to Z-up)
  ui/
    ZAASettings.qml    # Settings dialog (UM/Cura themed)
```

Core modules (`gcode_parser`, `ray_caster`, `contouring`, `collision`) are pure Python/numpy with no Cura dependencies and are fully testable standalone.

## Running Tests

Requires Python 3.10+ with `numpy` and `pytest`:

```bash
# With uv
uv run --with pytest --with numpy pytest tests/ -v

# Or with pip
pip install numpy pytest
pytest tests/ -v
```

Tests also run automatically via GitHub Actions on push/PR.

## Key Technical Decisions

- **Pure numpy ray-caster** instead of trimesh -- avoids C extension portability issues with Cura's embedded Python
- **2D XY grid acceleration** instead of BVH -- vertical-only rays make XY bucketing optimal and simple
- **In-place gcode_list modification** -- follows the PostProcessingPlugin pattern
- **Marlin-first** -- G1 XYZE with all 4 axes; Klipper also handles this fine
- **Z smoothing** -- linearly spreads the Z transition across the full segment length instead of concentrating it at the edge, eliminating stair-stepping
- **Flow compensation** -- E values scaled by `local_layer_height / nominal_layer_height`, clamped to [0.5, 1.5] ratio (aligned with GCodeZAA approach)
- **Layer 0 protection** -- first layer is never contoured to preserve bed adhesion

## Known Limitations

- **Post-processing approach** -- the plugin modifies G-code after slicing, so it cannot change toolpath layout or wall ordering. Some artifacts on wall perimeters of complex geometry are expected.
- **Lateral wall detection** -- walls that pass over lower geometry may be incorrectly contoured in edge cases. A heuristic detects and skips these when all sub-points clamp to the floor.
- **Top surfaces only** -- only surfaces facing upward are contoured. Overhangs and bottom surfaces are not affected.

## References

- Paper: *"Anti-aliasing for fused filament deposition"* -- Hai-Chuan Song et al., arXiv:1609.03032
- Reference implementation: [GCodeZAA](https://github.com/Theaninova/GCodeZAA) (GPL-3.0)
- OrcaSlicer Z Contouring: [wiki](https://github.com/OrcaSlicer/OrcaSlicer/wiki/quality_settings_z_contouring)

## License

GPL-3.0. See [LICENSE](LICENSE).
