"""Generate tests/plc/cell.json: the sorting cell unit, end to end.

Run: python tests/plc/generators/cell.py tests/plc/cell.json
The cell runs in PRG_Main (GVL_Config.xCellEnabled). PRG_TestCell injects parts (photo-eye pulse,
then vision and decision messages), simulates the vacuum switch and can trigger faults.
full_cycle_three_parts is the Phase 1 exit test.
"""

import json
import sys

CMD = {"Reset": 1, "Start": 2, "Stop": 3, "Suspend": 6, "Unsuspend": 7, "Clear": 9}
MODE = {"Production": 1, "Manual": 3}
QUALITY = {"Ok": 1, "Scrap": 3}
CELL = "PRG_Main.fbCell."
T = "PRG_TestCell."


def cmd(name, wait_ms):
    return [{"write": {"GVL_Hmi.eCommand": CMD[name]}}, {"waitMs": wait_ms}]


def state(name):
    return {"expect": {"GVL_Bridge.eState": f"E_PackMLState.{name}"}}


def inject(cls, quality):
    return [
        {
            "write": {
                T + "usiInjClass": cls,
                T + "eInjQuality": QUALITY[quality],
                T + "xInject": True,
            }
        },
        {"waitMs": 300},
    ]


def start_from_stopped():
    return [*cmd("Reset", 3000), state("Idle"), *cmd("Start", 16000), state("Execute")]


def recover_to_stopped():
    return [*cmd("Clear", 4000), state("Stopped")]


cases = [
    {
        "name": "full_cycle_three_parts",
        "steps": [
            {"write": {T + "xActive": True, "GVL_Config.xCellEnabled": True}},
            {"waitMs": 500},
            state("Stopped"),
            *start_from_stopped(),
            *inject(0, "Ok"),
            {"waitMs": 9000},
            *inject(1, "Ok"),
            {"waitMs": 9000},
            *inject(0, "Scrap"),
            {"waitMs": 22000},
            {
                "expect": {
                    CELL + "aBins[0].uiCount": 1,
                    CELL + "aBins[1].uiCount": 1,
                    CELL + "aBins[4].uiCount": 1,
                    CELL + "fbAlarms.xErrorActive": False,
                    CELL + "fbAlarms.xCriticalActive": False,
                }
            },
            state("Execute"),
        ],
    },
    {
        "name": "stop_completes_at_home",
        "steps": [
            *cmd("Stop", 12000),
            state("Stopped"),
            {"expect": {CELL + "fbSeq.xIdleAtHome": True}},
        ],
    },
    {
        "name": "estop_during_transfer_keeps_vacuum",
        "steps": [
            *start_from_stopped(),
            {"write": {T + "xEStopOnTransfer": True}},
            *inject(1, "Ok"),
            {"waitMs": 16000},
            state("Aborted"),
            {"expect": {"GVL_Bridge.xVacuumOn": True, CELL + "fbRobot.xMoving": False}},
            {"write": {T + "xEStopOnTransfer": False, "GVL_Bridge.xEStopOk": True}},
            {"waitMs": 300},
            *recover_to_stopped(),
            # restart: the part still on the cup is placed in quarantine first
            *start_from_stopped(),
            {"waitMs": 8000},
            {
                "expect": {
                    CELL + "aBins[5].uiCount": 1,
                    "GVL_Bridge.xVacuumOn": False,
                    "GVL_Bridge.eState": "E_PackMLState.Execute",
                }
            },
            *cmd("Stop", 12000),
            state("Stopped"),
        ],
    },
    {
        "name": "door_open_in_production_aborts",
        "steps": [
            *start_from_stopped(),
            {"write": {"GVL_Bridge.xDoorClosed": False}},
            {"waitMs": 2000},
            state("Aborted"),
            {"write": {"GVL_Bridge.xDoorClosed": True}},
            {"waitMs": 300},
            *recover_to_stopped(),
        ],
    },
    {
        "name": "bin_full_suspends",
        "steps": [
            *start_from_stopped(),
            {"write": {"GVL_Bridge.axBinFull[0]": True}},
            {"waitMs": 9000},
            state("Suspended"),
            {"write": {"GVL_Bridge.axBinFull[0]": False}},
            {"waitMs": 12000},
            state("Execute"),
            *cmd("Stop", 12000),
            state("Stopped"),
        ],
    },
    {
        "name": "operator_suspend_holds_until_unsuspend",
        "steps": [
            *start_from_stopped(),
            *cmd("Suspend", 9000),
            state("Suspended"),
            {"waitMs": 2000},
            state("Suspended"),
            *cmd("Unsuspend", 12000),
            state("Execute"),
            *cmd("Stop", 12000),
            state("Stopped"),
        ],
    },
    {
        "name": "restart_after_vacuum_loss",
        "steps": [
            *start_from_stopped(),
            {"write": {T + "xVacLostOnTransfer": True}},
            *inject(0, "Ok"),
            {"waitMs": 16000},
            state("Stopped"),
            {"expect": {CELL + "fbRobot.xMoving": False, CELL + "fbConv.lrActVelocity": 0}},
            {"write": {T + "xVacLostOnTransfer": False}},
            {"waitMs": 300},
            *start_from_stopped(),
            {"expect": {CELL + "ePickStep": "E_PickStep.WaitPart"}},
            *cmd("Stop", 12000),
            state("Stopped"),
        ],
    },
    {
        "name": "manual_jog_only_in_manual",
        "steps": [
            *start_from_stopped(),
            {"write": {T + "xMark": True}},
            {"waitMs": 300},
            {"write": {"GVL_Hmi.axJogPlus[1]": True}},
            {"waitMs": 1500},
            {"write": {"GVL_Hmi.axJogPlus[1]": False}},
            {"expect": {T + "lrJ1Delta": {"op": "=", "value": 0, "tolerance": 0.01}}},
            *cmd("Stop", 12000),
            state("Stopped"),
            {"write": {"GVL_Hmi.eModeRequest": MODE["Manual"]}},
            {"waitMs": 500},
            {"expect": {"GVL_Bridge.eMode": "E_PackMLMode.Manual"}},
            *cmd("Reset", 3000),
            *cmd("Start", 3000),
            state("Execute"),
            {"write": {T + "xMark": True}},
            {"waitMs": 300},
            {"write": {"GVL_Hmi.axJogPlus[1]": True}},
            {"waitMs": 1500},
            {"write": {"GVL_Hmi.axJogPlus[1]": False}},
            {"waitMs": 500},
            {"expect": {T + "lrJ1Delta": {"op": ">", "value": 5}}},
            *cmd("Stop", 3000),
            {"write": {"GVL_Hmi.eModeRequest": MODE["Production"], T + "xActive": False}},
            {"waitMs": 500},
            {"expect": {"GVL_Bridge.eMode": "E_PackMLMode.Production"}},
        ],
    },
]

with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as f:
    json.dump({"cases": cases}, f, indent=2)
    f.write("\n")
print(len(cases), "cases")
