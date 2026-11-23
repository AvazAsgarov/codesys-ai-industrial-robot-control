# CODESYS IronPython 2.7 script (runs inside CODESYS, not in the uv environment).
# Switches the root PLC device of RobotCell.project to "CODESYS Control Win V3 x64".
#
# Usage (CODESYS closed, project not open elsewhere):
#   "C:\Program Files\CODESYS 3.5.22.40\CODESYS\Common\CODESYS.exe"
#       --profile="CODESYS V3.5 SP22 Patch 4" --noUI --runscript="plc\scripts\set_device_x64.py"
# Result is written to plc/set_device_x64.log (git-ignored).
from __future__ import print_function

import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.environ.get("ROBOTCELL_PROJECT", os.path.join(HERE, "..", "RobotCell.project"))
LOG = os.path.join(HERE, "..", "set_device_x64.log")

CONTROL_WIN_X64 = (4096, "0000 0004", "3.5.22.40")

with open(LOG, "w") as log:
    try:
        proj = projects.open(PROJECT)  # noqa: F821 - "projects" is injected by CODESYS
        dev = [o for o in proj.get_children() if o.is_device][0]
        before = dev.get_device_identification()
        log.write("before: %s %s %s\n" % (before.type, before.id, before.version))
        dev.update(*CONTROL_WIN_X64)
        after = dev.get_device_identification()
        log.write("after: %s %s %s\n" % (after.type, after.id, after.version))
        proj.save()
        proj.close()
        log.write("OK\n")
    except Exception as exc:
        log.write("ERROR: %r\n" % (exc,))
