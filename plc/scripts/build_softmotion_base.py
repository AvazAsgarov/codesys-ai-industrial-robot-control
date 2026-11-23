# CODESYS IronPython 2.7 script (runs inside CODESYS, not in the uv environment).
#
# Builds the SoftMotion base of RobotCell.project reproducibly.
#
# Why: CODESYS accepts a "SoftMotion General Axis Pool" only on a device that was created with
# SoftMotion; a device made from the plain Standard.project template refuses it. The official
# SoftMotion tutorial "Robotics_Jogging" has such a device with a 6-axis articulated robot, so
# this script derives our base from it:
#   1. open the example with a full version update (compiler + libraries -> this CODESYS),
#   2. move the device to CODESYS Control Win V3 x64 and the pool/drives to their newest versions,
#   3. strip the example's application, visualization and root objects,
#   4. rename the drives to Axis_J1..Axis_J6, drop its additional axes, add Axis_Conveyor,
#   5. import our axis group (templates/AxisGroup_Robot.export) with the cell's kinematics,
#   6. save to ROBOTCELL_BASE_OUT (default: plc/RobotCell.base.project).
#
# Usage (CODESYS closed):
#   CODESYS.exe --profile="CODESYS V3.5 SP22 Patch 4" --noUI --runscript="plc\scripts\build_softmotion_base.py"
# The rest of the project (task configuration, folders, POUs) is created with the CODESYS MCP
# toolkit afterwards; see plc/scripts/README.md.
from __future__ import print_function

import os
import shutil
import stat
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
CODESYS_ROOT = r"C:\Program Files\CODESYS 3.5.22.40\CODESYS"
EXAMPLE = os.path.join(CODESYS_ROOT, "CODESYS SoftMotion", "Examples", "Tutorial", "Robotics_Jogging.project")
OUT = os.environ.get("ROBOTCELL_BASE_OUT", os.path.join(HERE, "..", "RobotCell.base.project"))
WORK = OUT + ".work"
TEMPLATE = os.path.join(HERE, "templates", "AxisGroup_Robot.export")
LOG = os.path.join(HERE, "..", "build_softmotion_base.log")

CONTROL_WIN_X64 = (4096, "0000 0004", "3.5.22.40")

# Kin_ArticulatedRobot_6DOF parameters in mm (spec: phase 1 plan, "Cell constants").
KINEMATICS = {"a1": "50", "d1": "400", "a2": "450", "a3": "50", "d3": "0", "d4": "450", "d6": "120"}

DELETE_APP = ["GroupJog2", "PLC_PRG", "Trace", "Visualization", "Visualization Manager", "Scene",
              "__VisualizationStyle", "Robi"]
DELETE_ROOT = ["ArrowX", "Frame", "ArrowZ", "LinearAxis", "RotaryAxis", "GlobalTextList",
               "__VisualizationStyle"]
DELETE_ROOT_LIBS = ("Depictor",)
RENAME = dict(("Drive_A%d" % i, "Axis_J%d" % i) for i in range(1, 7))


def version_key(v):
    return [int(x) if x.isdigit() else 0 for x in str(v).split(".")]


def update_to_newest(dev):
    did = dev.get_device_identification()
    same = [d.device_id for d in device_repository.get_all_devices()  # noqa: F821
            if d.device_id.type == did.type and str(d.device_id.id) == str(did.id)]
    if same:
        newest = max(same, key=lambda x: version_key(x.version))
        if version_key(newest.version) > version_key(did.version):
            dev.update(newest)


def main(log):
    shutil.copyfile(EXAMPLE, WORK)
    os.chmod(WORK, stat.S_IWRITE | stat.S_IREAD)
    flags = VersionUpdateFlags  # noqa: F821 - injected by CODESYS
    proj = projects.open(WORK, update_flags=flags.UpdateAll | flags.SilentMode)  # noqa: F821
    device = [o for o in proj.get_children(False) if o.is_device][0]
    device.update(*CONTROL_WIN_X64)
    pool = proj.find("SoftMotion General Axis Pool", True)[0]
    update_to_newest(pool)
    for drive in pool.get_children(False):
        update_to_newest(drive)

    app = proj.find("Application", True)[0]
    for name in DELETE_APP:
        for obj in app.find(name, False):
            obj.remove()
    for obj in list(proj.get_children(False)):
        if obj.get_name() in DELETE_ROOT:
            obj.remove()
        elif obj.get_name() == "Library Manager":
            for ref in list(obj.references):
                if any(token in ref.name for token in DELETE_ROOT_LIBS):
                    obj.remove_library(ref.name)

    for drive in list(pool.get_children(False)):
        name = drive.get_name()
        if name.startswith("AddAxis_"):
            drive.remove()
        elif name in RENAME:
            drive.rename(RENAME[name])
    j1 = pool.find("Axis_J1", False)[0].get_device_identification()
    pool.add("Axis_Conveyor", j1.type, j1.id, j1.version)

    with open(TEMPLATE) as f:
        export = f.read()
    for key, value in KINEMATICS.items():
        export = export.replace("{%s}" % key, value)
    generated = OUT + ".AxisGroup_Robot.export"
    with open(generated, "w") as f:
        f.write(export)
    app.import_native(generated)
    os.remove(generated)

    proj.save_as(OUT)
    proj.close()
    os.remove(WORK)
    log.write("OK: %s\n" % OUT)


with open(LOG, "w") as log_file:
    try:
        main(log_file)
    except Exception:
        log_file.write("ERROR\n" + traceback.format_exc())
