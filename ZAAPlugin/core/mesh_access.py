"""Extract and transform mesh data from Cura's scene for ray-casting.

This module imports Cura/Uranium APIs and is NOT testable outside of Cura.
All coordinate transformation logic (Y-up -> Z-up, bed offset) lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from UM.Scene.SceneNode import SceneNode

from UM.Logger import Logger


def extract_meshes(scene) -> list[tuple[np.ndarray, np.ndarray]]:
    """Extract all sliceable meshes from the Cura scene.

    Returns a list of (vertices, indices) tuples in G-code coordinate system
    (Z-up, with bed offset applied).
    """
    from cura.CuraApplication import CuraApplication
    from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator

    root = scene.getRoot()
    meshes: list[tuple[np.ndarray, np.ndarray]] = []

    for node in DepthFirstIterator(root):
        # Skip non-sliceable nodes (groups, camera, build plate, etc.)
        if not hasattr(node, "callDecoration"):
            continue
        if not node.callDecoration("isSliceable"):
            continue

        mesh_data = node.getMeshDataTransformed()
        if mesh_data is None:
            continue

        verts = mesh_data.getVertices()
        if verts is None or len(verts) == 0:
            continue

        indices = mesh_data.getIndices()
        if indices is None:
            # Non-indexed mesh: sequential trios of vertices form triangles
            n_verts = len(verts)
            n_tris = n_verts // 3
            indices = np.arange(n_tris * 3, dtype=np.int64).reshape(-1, 3)

        # Convert Uranium Y-up to G-code Z-up
        # Uranium: X = right, Y = up, Z = towards camera
        # G-code:  X = right, Y = depth, Z = up
        # Mapping: gcode_x = uranium_x, gcode_y = -uranium_z, gcode_z = uranium_y
        verts_zup = np.column_stack([
            verts[:, 0],      # X stays X
            -verts[:, 2],     # Y = -Z_uranium
            verts[:, 1],      # Z = Y_uranium (height)
        ])

        # Apply bed center offset
        verts_zup = _apply_bed_offset(verts_zup)

        meshes.append((verts_zup.astype(np.float64), indices.astype(np.int64)))

    Logger.log("d", f"ZAA: Extracted {len(meshes)} mesh(es) from scene")
    return meshes


def _apply_bed_offset(verts: np.ndarray) -> np.ndarray:
    """Add the build plate origin offset to vertex coordinates.

    When machine_center_is_zero is False (most printers), the Cura scene
    origin is at the center of the bed, but G-code origin is at the corner.
    We need to shift X and Y by half the bed dimensions.
    """
    from cura.CuraApplication import CuraApplication

    app = CuraApplication.getInstance()
    global_stack = app.getGlobalContainerStack()

    if global_stack is None:
        Logger.log("w", "ZAA: No global container stack, skipping bed offset")
        return verts

    center_is_zero = global_stack.getProperty("machine_center_is_zero", "value")

    if not center_is_zero:
        width = global_stack.getProperty("machine_width", "value")
        depth = global_stack.getProperty("machine_depth", "value")
        verts = verts.copy()
        verts[:, 0] += width / 2.0
        verts[:, 1] += depth / 2.0

    return verts


def merge_meshes(
    mesh_list: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    """Concatenate multiple meshes into a single vertex/index pair.

    Offsets indices for each subsequent mesh so they reference the correct
    vertices in the combined array.
    """
    if not mesh_list:
        return np.empty((0, 3), dtype=np.float64), np.empty((0, 3), dtype=np.int64)

    if len(mesh_list) == 1:
        return mesh_list[0]

    all_verts: list[np.ndarray] = []
    all_indices: list[np.ndarray] = []
    vertex_offset = 0

    for verts, indices in mesh_list:
        all_verts.append(verts)
        all_indices.append(indices + vertex_offset)
        vertex_offset += len(verts)

    return (
        np.vstack(all_verts).astype(np.float64),
        np.vstack(all_indices).astype(np.int64),
    )
