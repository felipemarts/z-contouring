# Z Anti-Aliasing (ZAA) Plugin for Cura

A Cura 5.x Extension plugin that reduces stair-stepping on curved top surfaces by varying the Z height within a layer to follow the actual mesh surface.

Unlike external tools that require manual STL export, this plugin accesses the 3D mesh directly from Cura's scene -- no extra steps needed.

## How It Works

1. After slicing, the plugin intercepts the G-code before it is saved/sent
2. For each extrusion move in target regions (e.g. `TOP-SURFACE-SKIN`), the segment is subdivided into fine sub-points
3. A vertical ray is cast at each sub-point against the original mesh to find the true surface Z
4. The flat Z is replaced with the contoured Z (clamped within `max_contour` of the nominal layer height)
5. Extrusion (E) values are adjusted to compensate for the varying local layer height
6. A collision checker prevents the nozzle from descending into previously deposited material

```
; Before (flat layer)
G1 X10.0 Y10.0 E0.5

; After (contoured)
G1 X10.2 Y10.0 Z2.97 E0.048
G1 X10.4 Y10.0 Z2.95 E0.047
G1 X10.6 Y10.0 Z2.94 E0.046
```

## Installation

Copy the `ZAAPlugin/` folder into your Cura plugins directory:

- **Windows:** `%APPDATA%\cura\5.x\plugins\`
- **macOS:** `~/Library/Application Support/cura/5.x/plugins/`
- **Linux:** `~/.local/share/cura/5.x/plugins/`

Restart Cura. The plugin appears under **Extensions > Z Anti-Aliasing**.

## Settings

Access via **Extensions > Z Anti-Aliasing > Settings...**

| Setting | Default | Description |
|---------|---------|-------------|
| **Enabled** | On | Enable/disable ZAA processing |
| **Max contour depth** | 0 (auto) | Maximum Z drop below nominal. 0 = half of layer height |
| **Resolution** | 0.5 mm | Subdivision spacing along extrusion segments |
| **Target regions** | TOP-SURFACE-SKIN | G-code region types to process |
| **Collision detection** | On | Prevent nozzle crashes with deposited material |

## Architecture

```
ZAAPlugin/
  __init__.py          # Plugin entry point (deferred Cura imports)
  plugin.json          # Cura plugin metadata (API 8)
  ZAAExtension.py      # Extension class: menu, preferences, orchestration
  core/
    gcode_parser.py    # G-code parsing, formatting, state tracking
    ray_caster.py      # Vertical ray-mesh intersection with 2D grid acceleration
    contouring.py      # Subdivision, Z replacement, flow compensation
    collision.py       # Spatial-hash nozzle collision checker
    mesh_access.py     # Extract meshes from Cura scene (Y-up to Z-up)
  ui/
    ZAASettings.qml    # Settings dialog
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

## Key Technical Decisions

- **Pure numpy ray-caster** instead of trimesh -- avoids C extension portability issues with Cura's embedded Python
- **2D XY grid acceleration** instead of BVH -- vertical-only rays make XY bucketing optimal and simple
- **In-place gcode_list modification** -- follows the PostProcessingPlugin pattern
- **Marlin-first** -- G1 XYZE with all 4 axes; Klipper also handles this fine

## References

- Paper: *"Anti-aliasing for fused filament deposition"* -- Hai-Chuan Song et al., arXiv:1609.03032
- Reference implementation: [GCodeZAA](https://github.com/Theaninova/GCodeZAA) (GPL-3.0)
- OrcaSlicer Z Contouring: [wiki](https://github.com/OrcaSlicer/OrcaSlicer/wiki/quality_settings_z_contouring)

## License

GPL-3.0. See [LICENSE](LICENSE).
