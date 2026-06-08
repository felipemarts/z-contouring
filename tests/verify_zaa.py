"""Verification script: compare disabled vs enabled G-code layer by layer.

The ZAA plugin targets TOP-SURFACE-SKIN, SKIN, and WALL-OUTER types.
It should only contour layers/segments where there IS an exposed top surface.
On layers with purely vertical walls (like the flat back of the Benchy),
Z should remain at nominal.

Usage:
    python verify_zaa.py                  # runs both ramp + benchy
    python verify_zaa.py ramp             # runs only the ramp example
    python verify_zaa.py benchy           # runs only the benchy example
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

PARAM_RE = re.compile(r"([XYZEF])([-+]?\d*\.?\d+)")
GCODE_CMD_RE = re.compile(r"^(G[01])\b")

# Types the plugin intentionally targets
TARGET_TYPES = {"TOP-SURFACE-SKIN", "SKIN", "WALL-OUTER"}


def parse_layers(filepath: str) -> dict[int, dict]:
    """Parse gcode into per-layer, per-type extrusion data.

    Returns {layer_num: {
        "nominal_z": float,
        "types": set[str],
        "extrusions": {type: [(z, x, y), ...]},
    }}
    """
    layers: dict[int, dict] = {}
    current_layer = -1
    current_type = ""
    current_z = 0.0

    with open(filepath, "r") as f:
        for line in f:
            stripped = line.strip()

            if stripped.startswith(";LAYER:"):
                try:
                    current_layer = int(stripped[7:])
                except ValueError:
                    pass
                if current_layer not in layers:
                    layers[current_layer] = {
                        "nominal_z": 0.0,
                        "types": set(),
                        "extrusions": defaultdict(list),
                    }
                continue

            if stripped.startswith(";TYPE:"):
                current_type = stripped[6:]
                if current_layer >= 0:
                    layers[current_layer]["types"].add(current_type)
                continue

            cmd_match = GCODE_CMD_RE.match(stripped)
            if not cmd_match:
                continue

            params = {}
            for m in PARAM_RE.finditer(stripped):
                params[m.group(1)] = float(m.group(2))

            if "Z" in params:
                current_z = params["Z"]

            cmd = cmd_match.group(1)

            if cmd == "G0" and "Z" in params and current_layer >= 0:
                if layers[current_layer]["nominal_z"] == 0.0:
                    layers[current_layer]["nominal_z"] = params["Z"]

            if cmd == "G1" and "E" in params and current_layer >= 0:
                x = params.get("X", 0.0)
                y = params.get("Y", 0.0)
                z = params.get("Z", current_z)
                layers[current_layer]["extrusions"][current_type].append((z, x, y))

    return layers


def extract_layer_height(filepath: str) -> float:
    with open(filepath, "r") as f:
        for line in f:
            m = re.search(r";Layer height: ([\d.]+)", line)
            if m:
                return float(m.group(1))
    return 0.2


def analyze_model(name: str, disabled_path: Path, enabled_path: Path) -> dict:
    """Run full analysis on a model pair. Returns summary dict."""
    print(f"\n{'#' * 90}")
    print(f"# MODEL: {name}")
    print(f"# Disabled: {disabled_path.name}")
    print(f"# Enabled:  {enabled_path.name}")
    print(f"{'#' * 90}")

    layer_height = extract_layer_height(str(disabled_path))
    print(f"\nLayer height: {layer_height}mm")

    print("\nParsing disabled gcode...")
    layers_d = parse_layers(str(disabled_path))
    print("Parsing enabled gcode...")
    layers_e = parse_layers(str(enabled_path))

    all_layers = sorted(set(layers_d.keys()) | set(layers_e.keys()))
    print(f"Total layers: {len(all_layers)}")

    # =================================================================
    # REPORT 1: Types inventory
    # =================================================================
    print("\n" + "=" * 90)
    print("REPORT 1: Types present in disabled gcode")
    print("=" * 90)

    all_types_seen = set()
    types_per_layer: dict[str, list[int]] = defaultdict(list)
    for ln in all_layers:
        if ln not in layers_d:
            continue
        for t in layers_d[ln]["types"]:
            all_types_seen.add(t)
            types_per_layer[t].append(ln)

    for t in sorted(all_types_seen):
        lyrs = types_per_layer[t]
        print(f"  ;TYPE:{t}: {len(lyrs)} layers (first={lyrs[0]}, last={lyrs[-1]})")

    layers_with_top_skin = types_per_layer.get("TOP-SURFACE-SKIN", [])
    print(f"\n  => TOP-SURFACE-SKIN present: {'YES' if layers_with_top_skin else 'NO'}")
    if layers_with_top_skin:
        print(f"     Layers: {layers_with_top_skin}")

    # =================================================================
    # REPORT 2: Per-layer Z changes
    # =================================================================
    print("\n" + "=" * 90)
    print("REPORT 2: Per-layer Z changes (enabled vs disabled)")
    print("=" * 90)

    z_leak_layers = []
    false_contour_layers = []
    ok_contour_layers = []
    collateral_layers = []
    # For the ramp: track every layer detail
    layer_details = []

    for ln in all_layers:
        if ln not in layers_d or ln not in layers_e:
            continue
        if ln <= 0:
            continue

        nominal_z = layers_d[ln]["nominal_z"]
        has_top_skin = "TOP-SURFACE-SKIN" in layers_d[ln]["types"]
        all_types = sorted(
            set(layers_d[ln]["extrusions"].keys()) | set(layers_e[ln]["extrusions"].keys())
        )

        layer_issues = []

        for typ in all_types:
            zd_vals = [z for z, x, y in layers_d[ln]["extrusions"].get(typ, [])]
            ze_vals = [z for z, x, y in layers_e[ln]["extrusions"].get(typ, [])]

            if not zd_vals and not ze_vals:
                continue

            z_min_d = min(zd_vals) if zd_vals else nominal_z
            z_max_d = max(zd_vals) if zd_vals else nominal_z
            z_min_e = min(ze_vals) if ze_vals else nominal_z
            z_max_e = max(ze_vals) if ze_vals else nominal_z

            has_change = abs(z_min_e - z_min_d) > 0.005 or abs(z_max_e - z_max_d) > 0.005

            is_target = typ in TARGET_TYPES
            delta_min = z_min_e - z_min_d
            delta_max = z_max_e - z_max_d

            detail = {
                "layer": ln,
                "type": typ,
                "is_target": is_target,
                "has_top_skin": has_top_skin,
                "z_range_d": (z_min_d, z_max_d),
                "z_range_e": (z_min_e, z_max_e),
                "n_moves_d": len(zd_vals),
                "n_moves_e": len(ze_vals),
                "delta_min": delta_min,
                "delta_max": delta_max,
                "changed": has_change,
                "nominal_z": nominal_z,
            }
            layer_details.append(detail)

            if has_change:
                if not is_target:
                    z_leak_layers.append(ln)
                elif not has_top_skin:
                    false_contour_layers.append(ln)
                else:
                    ok_contour_layers.append(ln)
                if not is_target and has_top_skin:
                    collateral_layers.append(ln)

                layer_issues.append(detail)

        if layer_issues:
            print(f"\n--- Layer {ln} (nominal Z={nominal_z:.4f}, top-skin={'YES' if has_top_skin else 'NO'}) ---")
            for issue in layer_issues:
                if not issue["is_target"]:
                    tag = "Z-LEAK"
                elif not issue["has_top_skin"]:
                    tag = "FALSE-CONTOUR"
                else:
                    tag = "OK"
                print(f"  [{tag:15s}] ;TYPE:{issue['type']}")
                print(f"    Disabled Z: [{issue['z_range_d'][0]:.4f}, {issue['z_range_d'][1]:.4f}] ({issue['n_moves_d']} moves)")
                print(f"    Enabled  Z: [{issue['z_range_e'][0]:.4f}, {issue['z_range_e'][1]:.4f}] ({issue['n_moves_e']} moves)")
                print(f"    Delta: min={issue['delta_min']:+.4f}, max={issue['delta_max']:+.4f}")

    z_leak_layers = sorted(set(z_leak_layers))
    false_contour_layers = sorted(set(false_contour_layers))
    ok_contour_layers = sorted(set(ok_contour_layers))
    collateral_layers = sorted(set(collateral_layers))

    # =================================================================
    # REPORT 3: Full layer overview (all layers, changed or not)
    # =================================================================
    print("\n" + "=" * 90)
    print("REPORT 3: Full layer-by-layer overview")
    print("=" * 90)

    prev_nominal = 0.0
    for ln in all_layers:
        if ln not in layers_d or ln <= 0:
            continue
        nominal_z = layers_d[ln]["nominal_z"]
        types_in_layer = sorted(layers_d[ln]["types"])
        # Find changes for this layer
        changes = [d for d in layer_details if d["layer"] == ln and d["changed"]]
        unchanged = [d for d in layer_details if d["layer"] == ln and not d["changed"]]

        status = "CONTOURED" if changes else "unchanged"
        types_str = ", ".join(types_in_layer) if types_in_layer else "(empty)"

        line = f"  Layer {ln:3d} | Z={nominal_z:7.4f} (dz={nominal_z - prev_nominal:+.4f}) | {status:10s} | types: {types_str}"

        if changes:
            change_summary = []
            for c in changes:
                tag = "OK" if c["is_target"] and c["has_top_skin"] else "BUG"
                change_summary.append(
                    f"{c['type']}[{tag}]: Z=[{c['z_range_e'][0]:.4f},{c['z_range_e'][1]:.4f}]"
                )
            line += f"\n{'':14s}changes: {'; '.join(change_summary)}"

        print(line)
        prev_nominal = nominal_z

    # =================================================================
    # REPORT 4: ZAA_RESET analysis
    # =================================================================
    print("\n" + "=" * 90)
    print("REPORT 4: ZAA_RESET lines")
    print("=" * 90)

    reset_count = 0
    reset_layers: dict[int, int] = {}
    cl = -1
    with open(str(enabled_path), "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith(";LAYER:"):
                try:
                    cl = int(stripped[7:])
                except ValueError:
                    pass
            if "ZAA_RESET" in stripped:
                reset_count += 1
                reset_layers[cl] = reset_layers.get(cl, 0) + 1

    print(f"  Total ZAA_RESET lines: {reset_count}")
    print(f"  Layers with resets: {len(reset_layers)}")
    if reset_layers:
        top_reset = sorted(reset_layers.items(), key=lambda x: -x[1])[:15]
        for l, c in top_reset:
            print(f"    Layer {l}: {c} resets")

    # =================================================================
    # REPORT 5: Z contamination (non-target at wrong Z)
    # =================================================================
    print("\n" + "=" * 90)
    print("REPORT 5: Z contamination — non-target extrusions at wrong Z")
    print("=" * 90)

    contamination_count = 0
    contamination_layers: dict[int, list[str]] = {}
    cl = -1
    ct = ""
    last_z = 0.0
    nominal_z_r5 = 0.0

    with open(str(enabled_path), "r") as f:
        for line in f:
            stripped = line.strip()

            if stripped.startswith(";LAYER:"):
                try:
                    cl = int(stripped[7:])
                except ValueError:
                    pass
                continue

            if stripped.startswith(";TYPE:"):
                ct = stripped[6:]
                continue

            if "ZAA_RESET" in stripped:
                for m in PARAM_RE.finditer(stripped):
                    if m.group(1) == "Z":
                        last_z = float(m.group(2))
                continue

            cmd_match = GCODE_CMD_RE.match(stripped)
            if not cmd_match:
                continue

            params = {}
            for m in PARAM_RE.finditer(stripped):
                params[m.group(1)] = float(m.group(2))

            if "Z" in params:
                last_z = params["Z"]

            if cmd_match.group(1) == "G0" and "Z" in params:
                if cl >= 0 and cl in layers_d:
                    nominal_z_r5 = layers_d[cl]["nominal_z"]

            if cmd_match.group(1) == "G1" and "E" in params and ct not in TARGET_TYPES:
                effective_z = params.get("Z", last_z)
                if cl >= 0 and cl in layers_d and abs(effective_z - nominal_z_r5) > 0.01:
                    contamination_count += 1
                    if cl not in contamination_layers:
                        contamination_layers[cl] = []
                    if len(contamination_layers[cl]) < 3:
                        contamination_layers[cl].append(
                            f";TYPE:{ct} Z={effective_z:.4f} (nominal={nominal_z_r5:.4f}, delta={effective_z - nominal_z_r5:+.4f})"
                        )

    print(f"  Contaminated extrusion moves: {contamination_count}")
    print(f"  Layers with contamination: {len(contamination_layers)}")
    if contamination_layers:
        for l in sorted(contamination_layers.keys())[:20]:
            print(f"    Layer {l}:")
            for detail in contamination_layers[l]:
                print(f"      {detail}")

    # =================================================================
    # REPORT 6: E continuity check
    # =================================================================
    print("\n" + "=" * 90)
    print("REPORT 6: E (extrusion) continuity check")
    print("=" * 90)

    e_errors = 0
    prev_e = None
    with open(str(enabled_path), "r") as f:
        for line in f:
            stripped = line.strip()
            if "G92" in stripped:
                prev_e = None
                continue
            m = re.search(r"G1.*E([-\d.]+)", stripped)
            if m:
                e = float(m.group(1))
                if prev_e is not None and e < prev_e - 0.01:
                    # Check it's not a retraction (those have F1500 typically)
                    if "F1500 E" not in stripped and e >= 0:
                        e_errors += 1
                        if e_errors <= 5:
                            print(f"  E DROPPED: {prev_e:.5f} -> {e:.5f}: {stripped[:80]}")
                prev_e = e

    print(f"  E discontinuities (non-retraction): {e_errors}")

    # =================================================================
    # SUMMARY
    # =================================================================
    print("\n" + "=" * 90)
    print(f"SUMMARY for {name}")
    print("=" * 90)
    print(f"  Total layers: {len(all_layers)}")
    print(f"  Layer height: {layer_height}mm")
    print(f"  TOP-SURFACE-SKIN layers: {len(layers_with_top_skin)}")
    print(f"  OK contoured layers: {len(ok_contour_layers)}")
    print(f"  [BUG] Z-LEAK: {len(z_leak_layers)} layers")
    print(f"  [BUG] FALSE-CONTOUR: {len(false_contour_layers)} layers")
    print(f"  [WARN] Collateral: {len(collateral_layers)} layers")
    print(f"  Z contaminations: {contamination_count} moves")
    print(f"  E discontinuities: {e_errors}")

    return {
        "name": name,
        "total_layers": len(all_layers),
        "z_leak": len(z_leak_layers),
        "false_contour": len(false_contour_layers),
        "ok_contour": len(ok_contour_layers),
        "contamination": contamination_count,
        "e_errors": e_errors,
    }


def main():
    base = Path(__file__).resolve().parent.parent / "examples"

    models = {
        "ramp": (
            base / "example_disabled_zaa.gcode",
            base / "example_enabled_zaa.gcode",
        ),
        "benchy": (
            base / "3DBenchy_disabled.gcode",
            base / "3DBenchy_enabled.gcode",
        ),
    }

    # Parse CLI args
    requested = sys.argv[1:] if len(sys.argv) > 1 else list(models.keys())
    results = []

    for model_name in requested:
        if model_name not in models:
            print(f"Unknown model: {model_name}. Available: {list(models.keys())}")
            sys.exit(2)
        disabled, enabled = models[model_name]
        if not disabled.exists() or not enabled.exists():
            print(f"Skipping {model_name}: files not found")
            continue
        result = analyze_model(model_name, disabled, enabled)
        results.append(result)

    # =================================================================
    # FINAL VERDICT
    # =================================================================
    print("\n" + "#" * 90)
    print("FINAL VERDICT")
    print("#" * 90)

    any_bugs = False
    for r in results:
        has_bug = r["z_leak"] > 0 or r["false_contour"] > 0 or r["contamination"] > 0
        status = "FAIL" if has_bug else "PASS"
        if has_bug:
            any_bugs = True
        print(f"  [{status}] {r['name']}: "
              f"ok={r['ok_contour']}, "
              f"z-leak={r['z_leak']}, "
              f"false-contour={r['false_contour']}, "
              f"contamination={r['contamination']}, "
              f"e-errors={r['e_errors']}")

    sys.exit(1 if any_bugs else 0)


if __name__ == "__main__":
    main()
