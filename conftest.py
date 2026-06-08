"""Pytest conftest: alias ZAAPlugin -> ZAA_Plugin for backwards compat."""
import sys
import os

# Ensure project root is on sys.path
root = os.path.dirname(__file__)
if root not in sys.path:
    sys.path.insert(0, root)

# Import testable (pure Python/numpy) modules and alias old name
import ZAA_Plugin
import ZAA_Plugin.core
import ZAA_Plugin.core.ray_caster
import ZAA_Plugin.core.gcode_parser
import ZAA_Plugin.core.contouring
import ZAA_Plugin.core.collision

for key, mod in list(sys.modules.items()):
    if key.startswith("ZAA_Plugin"):
        alias = key.replace("ZAA_Plugin", "ZAAPlugin", 1)
        sys.modules[alias] = mod
