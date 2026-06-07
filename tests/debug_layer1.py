"""Debug: show exactly what happens to layer 1 WALL-OUTER."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from ZAAPlugin.core.ray_caster import RayCaster
from ZAAPlugin.core.contouring import subdivide_segment

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")

verts = np.load(os.path.join(EXAMPLES, "mesh_vertices.npy"))
indices = np.load(os.path.join(EXAMPLES, "mesh_indices.npy"))
caster = RayCaster(verts, indices, cell_size=2.0)

# Layer 1 WALL-OUTER: starts at (133.996, 110) goes to (51, 110)
# nominal_z = 0.9, layer_height = 0.6, max_contour = 0.6
nominal_z = 0.9
layer_height = 0.6
max_contour = 0.6
z_floor = nominal_z - max_contour * 0.5  # = 0.6
z_ceiling = nominal_z + max_contour  # = 1.5

print(f"nominal_z={nominal_z}, z_floor={z_floor}, z_ceiling={z_ceiling}")
print()

# Subdivide the segment
points = subdivide_segment(133.996, 110.0, 51.0, 110.0, 0.5)
hit_z = caster.hit_z_batch(points)

print(f"{'X':>8} {'Y':>8} {'hit_z':>8} {'result':>8} {'reason'}")
print("-" * 60)

for i in range(len(points)):
    x, y = points[i]
    hz = hit_z[i]
    if np.isnan(hz):
        result = nominal_z
        reason = "no hit"
    elif hz < z_floor:
        result = nominal_z
        reason = f"below floor ({z_floor})"
    elif hz > z_ceiling:
        result = nominal_z
        reason = f"above ceiling ({z_ceiling})"
    else:
        result = hz
        reason = "CONTOURED"

    if i < 10 or i > len(points) - 10 or abs(result - nominal_z) > 0.001:
        print(f"{x:8.2f} {y:8.2f} {hz:8.4f} {result:8.4f} {reason}")

print(f"\n... total {len(points)} points")

# Count how many are contoured vs nominal
n_contoured = sum(1 for i in range(len(points))
                  if not np.isnan(hit_z[i]) and z_floor <= hit_z[i] <= z_ceiling)
print(f"Contoured: {n_contoured}, Nominal: {len(points) - n_contoured}")
