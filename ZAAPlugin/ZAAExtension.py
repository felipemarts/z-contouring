"""Z Anti-Aliasing Extension for Cura.

Hooks into the G-code write pipeline, accesses the 3D mesh from the scene,
and applies non-planar Z contouring to smooth top surfaces.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject

from UM.Extension import Extension
from UM.Logger import Logger

from cura.CuraApplication import CuraApplication


class ZAAExtension(QObject, Extension):
    """Main extension class for Z Anti-Aliasing."""

    def __init__(self, parent=None) -> None:
        QObject.__init__(self, parent)
        Extension.__init__(self)

        self.setMenuName("Z Anti-Aliasing")
        self.addMenuItem("Settings...", self._showSettings)

        # Default settings
        self._enabled: bool = True
        self._max_contour: float = 0.0  # 0 = auto (0.5 * layer_height)
        self._resolution: float = 0.5  # mm
        self._target_types: set[str] = {"TOP-SURFACE-SKIN"}
        self._enable_collision: bool = True
        self._nozzle_diameter: float = 0.4

        # Register preferences
        self._initPreferences()

        # Connect to write signal
        app = CuraApplication.getInstance()
        app.getOutputDeviceManager().writeStarted.connect(self._postProcess)

        Logger.log("i", "ZAA: Z Anti-Aliasing plugin loaded")

    def _initPreferences(self) -> None:
        """Register plugin preferences with Cura."""
        prefs = CuraApplication.getInstance().getPreferences()
        prefs.addPreference("zaa/enabled", True)
        prefs.addPreference("zaa/max_contour", 0.0)
        prefs.addPreference("zaa/resolution", 0.5)
        prefs.addPreference("zaa/target_types", "TOP-SURFACE-SKIN")
        prefs.addPreference("zaa/enable_collision", True)

        self._loadPreferences()

    def _loadPreferences(self) -> None:
        """Load current preference values."""
        prefs = CuraApplication.getInstance().getPreferences()
        self._enabled = bool(prefs.getValue("zaa/enabled"))
        self._max_contour = float(prefs.getValue("zaa/max_contour"))
        self._resolution = float(prefs.getValue("zaa/resolution"))
        self._enable_collision = bool(prefs.getValue("zaa/enable_collision"))

        types_str = str(prefs.getValue("zaa/target_types"))
        self._target_types = {t.strip() for t in types_str.split(",") if t.strip()}

    def _showSettings(self) -> None:
        """Show the ZAA settings dialog."""
        # QML dialog will be loaded here in a future phase.
        # For now, log the current settings.
        Logger.log(
            "i",
            f"ZAA Settings: enabled={self._enabled}, "
            f"max_contour={self._max_contour}, "
            f"resolution={self._resolution}, "
            f"targets={self._target_types}, "
            f"collision={self._enable_collision}",
        )

    def _postProcess(self, output_device) -> None:
        """Main entry point: post-process G-code with Z Anti-Aliasing."""
        self._loadPreferences()

        if not self._enabled:
            Logger.log("d", "ZAA: Disabled, skipping")
            return

        # Get G-code from scene
        scene = CuraApplication.getInstance().getController().getScene()
        gcode_dict = getattr(scene, "gcode_dict", None)
        if gcode_dict is None:
            Logger.log("w", "ZAA: No gcode_dict found in scene")
            return

        active_plate = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
        if active_plate not in gcode_dict:
            Logger.log("w", f"ZAA: Build plate {active_plate} not in gcode_dict")
            return

        gcode_list = gcode_dict[active_plate]

        # Prevent double-processing
        if gcode_list and ";ZAA_APPLIED" in gcode_list[0]:
            Logger.log("d", "ZAA: Already applied, skipping")
            return

        Logger.log("i", "ZAA: Starting Z Anti-Aliasing post-processing...")

        try:
            self._applyZAA(gcode_list)
        except Exception:
            Logger.logException("e", "ZAA: Error during post-processing")
            return

        # Mark as processed
        gcode_list[0] += ";ZAA_APPLIED\n"
        gcode_dict[active_plate] = gcode_list
        setattr(scene, "gcode_dict", gcode_dict)

        Logger.log("i", "ZAA: Post-processing complete")

    def _applyZAA(self, gcode_list: list[str]) -> None:
        """Run the full ZAA pipeline on the G-code."""
        from .core.mesh_access import extract_meshes, merge_meshes
        from .core.ray_caster import RayCaster
        from .core.contouring import apply_zaa
        from .core.collision import CollisionChecker

        # Step 1: Extract meshes from scene
        scene = CuraApplication.getInstance().getController().getScene()
        mesh_list = extract_meshes(scene)

        if not mesh_list:
            Logger.log("w", "ZAA: No meshes found in scene, skipping")
            return

        # Step 2: Merge all meshes and build ray-caster
        vertices, indices = merge_meshes(mesh_list)
        Logger.log(
            "d",
            f"ZAA: Mesh has {len(vertices)} vertices, {len(indices)} triangles",
        )

        caster = RayCaster(vertices, indices, cell_size=2.0)

        # Step 3: Determine layer height and max contour
        global_stack = CuraApplication.getInstance().getGlobalContainerStack()
        layer_height = float(global_stack.getProperty("layer_height", "value"))

        max_contour = self._max_contour
        if max_contour <= 0:
            max_contour = 0.5 * layer_height

        Logger.log(
            "d",
            f"ZAA: layer_height={layer_height}, max_contour={max_contour}, "
            f"resolution={self._resolution}",
        )

        # Step 4: Set up collision checker
        collision_checker = None
        if self._enable_collision:
            nozzle_diam = float(
                global_stack.getProperty("machine_nozzle_size", "value")
            )
            collision_checker = CollisionChecker(nozzle_diameter=nozzle_diam)

        # Step 5: Apply contouring
        apply_zaa(
            gcode_list=gcode_list,
            caster=caster,
            layer_height=layer_height,
            max_contour=max_contour,
            resolution=self._resolution,
            target_types=self._target_types,
            collision_checker=collision_checker,
        )
