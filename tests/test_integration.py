"""Integration test: apply ZAA to the example gcode and compare."""
import sys
import os
import struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from ZAAPlugin.core.ray_caster import RayCaster
from ZAAPlugin.core.contouring import apply_zaa
from ZAAPlugin.core.collision import CollisionChecker


def parse_binary_stl(path):
    """Parse a binary STL file into vertices and indices."""
    with open(path, "rb") as f:
        f.read(80)  # header
        n_tris = struct.unpack("<I", f.read(4))[0]
        vertices = []
        indices = []
        for i in range(n_tris):
            f.read(12)  # normal
            for j in range(3):
                x, y, z = struct.unpack("<fff", f.read(12))
                vertices.append([x, y, z])
                indices.append(i * 3 + j)
            f.read(2)  # attribute
    verts = np.array(vertices, dtype=np.float64)
    idx = np.arange(len(vertices), dtype=np.int64).reshape(-1, 3)
    return verts, idx


def main():
    base_dir = os.path.join(os.path.dirname(__file__), "..", "examples")

    # Load mesh
    stl_path = os.path.join(base_dir, "example.stl")
    verts, indices = parse_binary_stl(stl_path)
    print(f"Mesh: {len(verts)} vertices, {len(indices)} triangles")
    print(f"  X range: {verts[:,0].min():.1f} to {verts[:,0].max():.1f}")
    print(f"  Y range: {verts[:,1].min():.1f} to {verts[:,1].max():.1f}")
    print(f"  Z range: {verts[:,2].min():.1f} to {verts[:,2].max():.1f}")

    # The STL is in Cura/Uranium coords (Y-up). Convert to gcode coords (Z-up).
    # gcode_x = uranium_x, gcode_y = -uranium_z, gcode_z = uranium_y
    verts_zup = np.column_stack([
        verts[:, 0],
        -verts[:, 2],
        verts[:, 1],
    ])

    # Apply bed center offset (assume 200x200 bed, center_is_zero=false)
    # We need to match what Cura does. Let's check the gcode coordinates first.
    print(f"\nAfter Y-up to Z-up conversion:")
    print(f"  X range: {verts_zup[:,0].min():.1f} to {verts_zup[:,0].max():.1f}")
    print(f"  Y range: {verts_zup[:,1].min():.1f} to {verts_zup[:,1].max():.1f}")
    print(f"  Z range: {verts_zup[:,2].min():.1f} to {verts_zup[:,2].max():.1f}")

    # Read gcode to find the actual coordinate range used
    disabled_path = os.path.join(base_dir, "example_disabled_zaa.gcode")
    with open(disabled_path, "r") as f:
        gcode_text = f.read()

    # Parse MINX/MAXX from header
    for line in gcode_text.split("\n")[:15]:
        if line.startswith(";MIN") or line.startswith(";MAX"):
            print(f"  GCode header: {line}")

    # Apply bed offset to match gcode coords
    # From the gcode: MINX:43, MAXX:153.249, MINY:82, MAXY:118
    # The mesh center in XY should map to bed center
    # For a 200x200 bed: offset = 100
    # For a 235x235 bed: offset = 117.5
    # Let's compute: mesh center X = (min+max)/2, gcode center X = (43+153.249)/2 = 98.1
    mesh_cx = (verts_zup[:, 0].min() + verts_zup[:, 0].max()) / 2
    mesh_cy = (verts_zup[:, 1].min() + verts_zup[:, 1].max()) / 2
    gcode_cx = (43 + 153.249) / 2
    gcode_cy = (82 + 118) / 2

    offset_x = gcode_cx - mesh_cx
    offset_y = gcode_cy - mesh_cy
    print(f"\n  Computed bed offset: X={offset_x:.1f}, Y={offset_y:.1f}")

    verts_zup[:, 0] += offset_x
    verts_zup[:, 1] += offset_y

    print(f"\nFinal mesh coords (should match gcode):")
    print(f"  X range: {verts_zup[:,0].min():.1f} to {verts_zup[:,0].max():.1f}")
    print(f"  Y range: {verts_zup[:,1].min():.1f} to {verts_zup[:,1].max():.1f}")
    print(f"  Z range: {verts_zup[:,2].min():.1f} to {verts_zup[:,2].max():.1f}")

    # Build ray caster
    caster = RayCaster(verts_zup, indices, cell_size=2.0)

    # Test a few ray casts
    print("\nRay cast tests:")
    for x, y in [(98.0, 100.0), (50.0, 100.0), (145.0, 100.0), (130.0, 100.0)]:
        result = caster.hit_z(x, y)
        if result is not None:
            z, nz = result
            print(f"  hit_z({x}, {y}) = z={z:.4f}, nz={nz:.4f}")
        else:
            print(f"  hit_z({x}, {y}) = None")

    # Load gcode as list (Cura format: one big string per chunk)
    # Cura splits gcode by ";LAYER:" markers but for simplicity use one chunk
    gcode_list = [gcode_text]

    # Apply ZAA
    layer_height = 0.6
    max_contour = 0.3  # half layer height
    resolution = 0.5
    target_types = {"TOP-SURFACE-SKIN", "SKIN", "WALL-OUTER"}

    collision_checker = CollisionChecker(nozzle_diameter=0.4)

    print(f"\nApplying ZAA: layer_height={layer_height}, max_contour={max_contour}, resolution={resolution}")
    print(f"  Target types: {target_types}")

    apply_zaa(
        gcode_list=gcode_list,
        caster=caster,
        layer_height=layer_height,
        max_contour=max_contour,
        resolution=resolution,
        target_types=target_types,
        collision_checker=collision_checker,
    )

    # Save result
    enabled_path = os.path.join(base_dir, "example_enabled_zaa.gcode")
    with open(enabled_path, "w") as f:
        f.write(gcode_list[0])

    # Count ZAA markers
    zaa_resets = gcode_list[0].count("ZAA_RESET")
    print(f"\nResult: {zaa_resets} ZAA_RESET markers")

    # Show some contoured lines
    lines = gcode_list[0].split("\n")
    print("\nSample contoured sections:")
    for i, line in enumerate(lines):
        if "ZAA_RESET" in line:
            start = max(0, i - 4)
            for j in range(start, i + 1):
                print(f"  {lines[j]}")
            print()
            break

    # Compare Z ranges per layer
    print("Z values per layer:")
    current_layer = None
    layer_zs = {}
    for line in lines:
        if line.startswith(";LAYER:"):
            current_layer = line.strip()
            if current_layer not in layer_zs:
                layer_zs[current_layer] = []
        elif current_layer and "G1" in line and "Z" in line:
            import re
            m = re.search(r"Z([\d.]+)", line)
            if m:
                z = float(m.group(1))
                if z < 20:  # skip initial Z15 move
                    layer_zs[current_layer].append(z)

    for layer, zs in sorted(layer_zs.items()):
        if zs:
            print(f"  {layer}: Z min={min(zs):.4f}, max={max(zs):.4f}, unique={len(set(f'{z:.4f}' for z in zs))}")


if __name__ == "__main__":
    main()
