"""Generate tests/plc/packml.json: python tests/plc/generators/packml.py tests/plc/packml.json."""

import json
import sys

P = "PRG_TestPackML.fbSm."


def st(name):
    return f"E_PackMLState.{name}"


CMD = {
    "None": 0,
    "Reset": 1,
    "Start": 2,
    "Stop": 3,
    "Hold": 4,
    "Unhold": 5,
    "Suspend": 6,
    "Unsuspend": 7,
    "Abort": 8,
    "Clear": 9,
    "Complete": 10,
}
MODE = {"Production": 1, "Maintenance": 2, "Manual": 3}


def cmd(name):
    # Enums are written as their integer values; expectations use the symbolic names.
    return [{"write": {P + "eCommand": CMD[name]}}, {"cycles": 2}]


def none():
    return [{"write": {P + "eCommand": CMD["None"]}}, {"cycles": 1}]


def complete():
    return [
        {"write": {P + "xStateComplete": True}},
        {"cycles": 2},
        {"write": {P + "xStateComplete": False}},
        {"cycles": 1},
    ]


def expect_state(name):
    return [{"expect": {P + "eState": st(name)}}]


def reinit():
    return [{"write": {"PRG_TestPackML.xReinit": True}}, {"cycles": 3}] + expect_state("Stopped")


def to_execute():
    return (
        reinit()
        + cmd("Reset")
        + none()
        + complete()
        + expect_state("Idle")
        + cmd("Start")
        + none()
        + complete()
        + expect_state("Execute")
    )


cases = [
    {
        "name": "reset_start_reaches_execute",
        "steps": reinit()
        + cmd("Reset")
        + expect_state("Resetting")
        + none()
        + complete()
        + expect_state("Idle")
        + cmd("Start")
        + expect_state("Starting")
        + none()
        + complete()
        + expect_state("Execute"),
    },
    {
        "name": "stop_from_execute",
        "steps": to_execute()
        + cmd("Stop")
        + expect_state("Stopping")
        + none()
        + complete()
        + expect_state("Stopped"),
    },
    {
        "name": "abort_from_any_state",
        "steps": to_execute()
        + [{"write": {P + "xAbortRequest": True}}, {"cycles": 2}]
        + expect_state("Aborting")
        + [{"write": {P + "xAbortRequest": False}}, {"cycles": 1}]
        + complete()
        + expect_state("Aborted")
        + cmd("Reset")
        + expect_state("Aborted")
        + none()
        + cmd("Clear")
        + expect_state("Clearing")
        + none()
        + complete()
        + expect_state("Stopped"),
    },
    {
        "name": "hold_unhold",
        "steps": to_execute()
        + cmd("Hold")
        + expect_state("Holding")
        + none()
        + complete()
        + expect_state("Held")
        + cmd("Unhold")
        + expect_state("Unholding")
        + none()
        + complete()
        + expect_state("Execute"),
    },
    {
        "name": "suspend_on_starvation",
        "steps": to_execute()
        + [{"write": {P + "xSuspendRequest": True}}, {"cycles": 2}]
        + expect_state("Suspending")
        + [{"write": {P + "xSuspendRequest": False}}, {"cycles": 1}]
        + complete()
        + expect_state("Suspended")
        + [{"write": {P + "xUnsuspendRequest": True}}, {"cycles": 2}]
        + expect_state("Unsuspending")
        + [{"write": {P + "xUnsuspendRequest": False}}, {"cycles": 1}]
        + complete()
        + expect_state("Execute"),
    },
    {
        "name": "mode_change_only_when_allowed",
        "steps": to_execute()
        + [
            {"write": {P + "eModeRequest": MODE["Manual"]}},
            {"cycles": 2},
            {"expect": {P + "eMode": "E_PackMLMode.Production"}},
        ]
        + cmd("Stop")
        + none()
        + complete()
        + expect_state("Stopped")
        + [
            {"cycles": 2},
            {"expect": {P + "eMode": "E_PackMLMode.Manual"}},
            {"write": {P + "eModeRequest": MODE["Production"]}},
            {"cycles": 2},
            {"expect": {P + "eMode": "E_PackMLMode.Production"}},
        ],
    },
    {
        "name": "invalid_command_ignored",
        "steps": reinit()
        + cmd("Start")
        + expect_state("Stopped")
        + none()
        + cmd("Unhold")
        + expect_state("Stopped")
        + none(),
    },
]

with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as f:
    json.dump({"cases": cases}, f, indent=2)
    f.write("\n")
print(len(cases), "cases")
