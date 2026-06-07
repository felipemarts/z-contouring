"""Offline ZAA test: loads mesh dump + disabled gcode, applies ZAA, saves and validates."""
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from ZAAPlugin.core.ray_caster import RayCaster
from ZAAPlugin.core.contouring import apply_zaa
from ZAAPlugin.core.collision import CollisionChecker

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")


def load_mesh():
    verts = np.load(os.path.join(EXAMPLES, "mesh_vertices.npy"))
    indices = np.load(os.path.join(EXAMPLES, "mesh_indices.npy"))
    print(f"Mesh: {len(verts)} vertices, {len(indices)} triangles")
    print(f"  X: [{verts[:,0].min():.1f}, {verts[:,0].max():.1f}]")
    print(f"  Y: [{verts[:,1].min():.1f}, {verts[:,1].max():.1f}]")
    print(f"  Z: [{verts[:,2].min():.1f}, {verts[:,2].max():.1f}]")
    return verts, indices


def load_gcode(filename):
    path = os.path.join(EXAMPLES, filename)
    with open(path, "r") as f:
        return f.read()


def save_gcode(filename, text):
    path = os.path.join(EXAMPLES, filename)
    with open(path, "w") as f:
        f.write(text)
    print(f"Saved: {path}")


def extract_layer_height(gcode_text):
    m = re.search(r";Layer height: ([\d.]+)", gcode_text)
    return float(m.group(1)) if m else 0.2


def validate_output(disabled_text, enabled_text):
    """Compare disabled vs enabled gcode and report issues."""
    print("\n=== VALIDATION ===\n")

    # 1. Check ZAA was applied
    has_zaa = ";ZAA_APPLIED" in enabled_text
    print(f"ZAA_APPLIED marker: {'YES' if has_zaa else 'NO'}")

    # 2. Count ZAA_RESET
    resets = enabled_text.count("ZAA_RESET")
    print(f"ZAA_RESET count: {resets}")

    # 3. Check E continuity
    errors = 0
    prev_e = None
    for line in enabled_text.split("\n"):
        if "G92" in line:
            prev_e = None
            continue
        m = re.search(r"G1.*E([-\d.]+)", line)
        if m:
            e = float(m.group(1))
            if prev_e is not None and e < prev_e - 0.01 and "F1500 E" not in line:
                errors += 1
                if errors <= 3:
                    print(f"  E DROPPED: {prev_e:.3f} -> {e:.3f}: {line.strip()}")
            prev_e = e
    print(f"E discontinuities: {errors}")

    # 4. Compare total extrusion
    def final_e(text):
        last = 0
        for line in text.split("\n"):
            m = re.search(r"G1.*E([\d.]+)", line)
            if m:
                last = float(m.group(1))
        return last

    e_dis = final_e(disabled_text)
    e_en = final_e(enabled_text)
    print(f"Final E disabled: {e_dis:.3f}")
    print(f"Final E enabled:  {e_en:.3f}")
    print(f"E difference: {e_en - e_dis:.3f} ({(e_en/e_dis - 1)*100:.1f}%)")

    # 5. Per-layer Z analysis
    print("\n=== PER-LAYER Z ANALYSIS ===\n")
    layer_num = None
    nominal_z = None
    layer_z_values = {}

    for line in enabled_text.split("\n"):
        if line.startswith(";LAYER:"):
            layer_num = int(line[7:])
            layer_z_values[layer_num] = []
        if layer_num is not None:
            m = re.search(r"G[01].*Z([\d.]+)", line)
            if m:
                z = float(m.group(1))
                if z < 20:  # skip Z15 travel
                    layer_z_values[layer_num].append(z)

    # Get nominal Z per layer from disabled gcode
    layer_nominal = {}
    current_layer = None
    for line in disabled_text.split("\n"):
        if line.startswith(";LAYER:"):
            current_layer = int(line[7:])
        if current_layer is not None:
            m = re.search(r"G0.*Z([\d.]+)", line)
            if m:
                z = float(m.group(1))
                if z < 20 and current_layer not in layer_nominal:
                    layer_nominal[current_layer] = z

    for layer in sorted(layer_z_values.keys()):
        zs = layer_z_values[layer]
        nom = layer_nominal.get(layer, "?")
        if zs:
            z_min = min(zs)
            z_max = max(zs)
            changed = z_min != z_max or (nom != "?" and abs(z_min - nom) > 0.001)
            status = "CONTOURED" if changed else "unchanged"
            below_prev = ""
            if layer > 0 and nom != "?":
                prev_nom = layer_nominal.get(layer - 1, 0)
                if z_min < prev_nom - 0.01:
                    below_prev = f" *** Z_MIN BELOW PREV LAYER ({prev_nom}) ***"
            print(f"  Layer {layer}: nominal={nom}, Z=[{z_min:.4f}, {z_max:.4f}] {status}{below_prev}")
        else:
            print(f"  Layer {layer}: nominal={nom}, no Z moves")

    # 6. Check layer 0 untouched
    print("\n=== LAYER 0 CHECK ===\n")
    layer0_disabled = []
    layer0_enabled = []
    in_layer0 = False
    for line in disabled_text.split("\n"):
        if ";LAYER:0" in line:
            in_layer0 = True
        elif ";LAYER:1" in line:
            in_layer0 = False
        if in_layer0:
            layer0_disabled.append(line)
    in_layer0 = False
    for line in enabled_text.split("\n"):
        if ";LAYER:0" in line:
            in_layer0 = True
        elif ";LAYER:1" in line:
            in_layer0 = False
        if in_layer0:
            layer0_enabled.append(line)

    if layer0_disabled == layer0_enabled:
        print("Layer 0: IDENTICAL (good)")
    else:
        diffs = 0
        for i, (a, b) in enumerate(zip(layer0_disabled, layer0_enabled)):
            if a != b:
                diffs += 1
                if diffs <= 5:
                    print(f"  Layer 0 diff at line {i}:")
                    print(f"    disabled: {a}")
                    print(f"    enabled:  {b}")
        print(f"  Layer 0: {diffs} lines differ *** PROBLEM ***")


def main():
    # Load mesh
    verts, indices = load_mesh()

    # Test ray caster
    caster = RayCaster(verts, indices, cell_size=2.0)
    print("\nRay cast samples:")
    for x, y in [(50, 100), (98, 100), (130, 100), (145, 100)]:
        z = caster.hit_z(float(x), float(y))
        print(f"  hit_z({x}, {y}) = {z}")

    # Load disabled gcode
    disabled_text = load_gcode("example_disabled_zaa.gcode")
    layer_height = extract_layer_height(disabled_text)
    print(f"\nLayer height: {layer_height}")

    # Apply ZAA
    gcode_list = [disabled_text]
    max_contour = layer_height
    resolution = 0.5
    target_types = {"TOP-SURFACE-SKIN", "SKIN", "WALL-OUTER"}
    collision_checker = CollisionChecker(nozzle_diameter=0.4)

    print(f"Applying ZAA: max_contour={max_contour}, resolution={resolution}")
    print(f"Target types: {target_types}")

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
    save_gcode("example_enabled_zaa.gcode", gcode_list[0])

    # Validate
    validate_output(disabled_text, gcode_list[0])


if __name__ == "__main__":
    main()
