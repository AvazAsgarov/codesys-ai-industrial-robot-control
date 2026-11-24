"""Builds the operator screen descriptions (hmi/*.json) for the CODESYS HMI tool.

The screens bind only to GVL_HmiView / GVL_HmiPanel / GVL_Hmi / GVL_Bridge and the bin counters;
texts, permissives and state groups come from FB_HmiView (no logic in the visualization).
Run: python hmi/build_screens.py
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
ACCENT = "#2F5D8A"

# GVL_AlarmDefs order (row i = E_AlarmId i); ISA-18.2 priority prefix
ALARMS = [
    ("Emergency stop pressed", "critical"),
    ("Safety door opened in automatic mode", "critical"),
    ("Connection to the digital twin bridge lost", "critical"),
    ("Robot axis group error", "critical"),
    ("Conveyor axis error", "error"),
    ("Joint following error above warning limit", "warning"),
    ("Joint following error above fault limit", "critical"),
    ("Joint feedback not updated", "critical"),
    ("Vacuum not reached - part not gripped", "error"),
    ("Vacuum lost while carrying a part", "error"),
    ("Part left the pick window unpicked", "warning"),
    ("A bin is full - cell suspended until it is emptied", "warning"),
    ("No vision result for a captured part", "warning"),
    ("AI decision late - fallback rule used", "warning"),
    ("Low detection confidence - part quarantined", "warning"),
    ("Part queue full", "error"),
]
PREFIX = {"critical": "P1", "error": "P2", "warning": "P3"}
SEVERITY = {"critical": "alarm", "error": "alarm", "warning": "warning"}  # the tool's two tones
BINS = ["Type A", "Type B", "Type C", "Rework", "Scrap", "Quarantine"]
BIN_CAPACITY = 30
MAINT = {"min": "Maintenance"}

TONE = {"critical": "alarm", "error": "alarm", "warning": "warn"}


def alarm_lamps(rows: range) -> list[dict]:
    """Alarm rows as lamps (lit while active or unacknowledged), text with the priority prefix."""
    return [
        {
            "label": f"{PREFIX[ALARMS[i - 1][1]]} {ALARMS[i - 1][0]}",
            "on": f"GVL_HmiView.axAlarm[{i}]",
            "tone": TONE[ALARMS[i - 1][1]],
        }
        for i in rows
    ]


alarm_rows = [
    {"active": f"GVL_HmiView.axAlarm[{i}]", "text": f"{PREFIX[c]} {t}", "severity": SEVERITY[c]}
    for i, (t, c) in enumerate(ALARMS, start=1)
]

machine = {
    "states": [
        {"on": "GVL_HmiView.xAborted", "text": "Aborted", "tone": "alarm", "icon": "fault"},
        {"on": "GVL_HmiView.xHeld", "text": "Suspended", "tone": "warn", "icon": "pause"},
        {"on": "GVL_HmiView.xActing", "text": "Changing state", "tone": "warn"},
        {"on": "GVL_HmiView.xManual", "text": "Manual", "tone": "accent", "icon": "manual"},
        {"on": "GVL_HmiView.xExecute", "text": "Execute", "tone": "neutral", "icon": "play"},
        {"on": "GVL_HmiView.xIdle", "text": "Idle", "tone": "neutral"},
    ],
    "idle": {"text": "Stopped", "tone": "neutral", "icon": "stop"},
    "detail": "GVL_HmiView.sPickStep",
    "start": "GVL_HmiPanel.xStart",
    "stop": "GVL_HmiPanel.xStop",
    "reset": "GVL_HmiPanel.xReset",
    "mode": {
        "variable": "GVL_HmiPanel.iModeSelect",
        "options": ["Production", "Maintenance", "Manual"],
        "values": ["1", "2", "3"],
    },
}
info = [
    {"label": "State", "value": "GVL_HmiView.sState"},
    {"label": "Mode", "value": "GVL_HmiView.sMode"},
    {"label": "Placed", "value": "GVL_HmiView.uiPlaced", "unit": "parts"},
    {"label": "Newest alarm", "value": "GVL_HmiView.sNewestAlarm"},
]


def page(name: str, title: str, subtitle: str, icon: str, widgets: list) -> dict:
    """One page with the shared frame: top bar info and the machine bar."""
    return {
        "name": name,
        "title": title,
        "subtitle": subtitle,
        "icon": icon,
        "size": "1920x1080",
        "accent": ACCENT,
        "info": info,
        "machine": machine,
        "widgets": widgets,
    }


overview = page(
    "Overview",
    "Sorting cell",
    "Robot pick-and-place line",
    "home",
    [
        {
            "type": "line",
            "title": "Line",
            "at": [1, 1, 12, 2],
            "stations": [
                {
                    "name": "Conveyor",
                    "tag": "CV-101",
                    "symbol": "conveyor",
                    "on": "GVL_HmiView.xBeltRunning",
                    "fault": "GVL_HmiView.axAlarmActive[5]",
                    "value": "GVL_Bridge.lrBeltVel",
                    "unit": "mm/s",
                    "screen": "Robot",
                },
                {
                    "name": "Camera",
                    "tag": "PE-1",
                    "symbol": "camera",
                    "on": "GVL_Bridge.xPE1",
                    "warning": "GVL_HmiView.axAlarm[13]",
                    "screen": "Alarms",
                },
                {
                    "name": "Robot",
                    "tag": "R-1",
                    "symbol": "robot6",
                    "on": "GVL_HmiView.xRobotMoving",
                    "fault": "GVL_HmiView.axAlarmActive[4]",
                    "warning": "GVL_HmiView.axAlarmActive[6]",
                    "manual": "GVL_HmiView.xManual",
                    "screen": "Robot",
                },
                {
                    "name": "Gripper",
                    "tag": "VG-1",
                    "symbol": "gripper",
                    "on": "GVL_Bridge.xVacuumOn",
                    "fault": "GVL_HmiView.axAlarm[10]",
                    "warning": "GVL_HmiView.axAlarm[9]",
                    "screen": "Robot",
                },
                {
                    "name": "Bins",
                    "tag": "BN-1..6",
                    "symbol": "bin",
                    "on": "GVL_HmiView.xExecute",
                    "warning": "GVL_HmiView.xAnyBinFull",
                    "value": "GVL_HmiView.uiPlaced",
                    "unit": "parts",
                    "screen": "Alarms",
                },
            ],
        },
        {
            "type": "value",
            "title": "Belt speed",
            "icon": "speed",
            "at": [1, 3, 3, 3],
            "value": "GVL_Bridge.lrBeltVel",
            "unit": "mm/s",
            "decimals": 0,
            "min": 0,
            "max": 150,
            "trend": True,
        },
        {
            "type": "value",
            "title": "Parts placed",
            "icon": "count",
            "at": [4, 3, 3, 3],
            "value": "GVL_HmiView.uiPlaced",
            "unit": "parts",
            "decimals": 0,
            "trend": True,
        },
        *[
            {
                "type": "bar",
                "title": b,
                "at": [7 + i, 3, 1, 3],
                "value": f"PRG_Main.fbCell.aBins[{i}].uiCount",
                "min": 0,
                "max": BIN_CAPACITY,
                "unit": "parts",
                "decimals": 0,
                "bands": [
                    {"from": 0, "tone": "accent"},
                    {"from": BIN_CAPACITY - 3, "tone": "warn"},
                ],
            }
            for i, b in enumerate(BINS)
        ],
        {
            "type": "status",
            "title": "Safety and links",
            "icon": "info",
            "at": [1, 6, 3, 3],
            "items": [
                {"label": "E-stop released", "off": "E-STOP PRESSED", "on": "GVL_Bridge.xEStopOk"},
                {"label": "Door closed", "off": "DOOR OPEN", "on": "GVL_Bridge.xDoorClosed"},
                {
                    "label": "Twin bridge active",
                    "off": "Twin bridge off",
                    "on": "GVL_Bridge.xTwinActive",
                },
                {"label": "Vacuum OK", "off": "No vacuum", "on": "GVL_Bridge.xVacuumOk"},
                {"label": "Part at PE-1", "off": "PE-1 free", "on": "GVL_Bridge.xPE1"},
            ],
        },
        {
            "type": "status",
            "title": "Safety alarms",
            "icon": "alarm",
            "at": [4, 6, 3, 3],
            "items": alarm_lamps(range(1, 6)),
        },
        {
            "type": "status",
            "title": "Process alarms",
            "icon": "alarm",
            "at": [7, 6, 3, 3],
            "items": alarm_lamps((7, 8, 9, 10, 12)),
        },
        {
            "type": "buttons",
            "title": "Commands",
            "at": [10, 6, 3, 3],
            "items": [
                {"label": "Acknowledge", "variable": "GVL_HmiPanel.xAckAll", "icon": "check"},
                {"label": "Suspend", "variable": "GVL_HmiPanel.xSuspend", "icon": "pause"},
                {"label": "Unsuspend", "variable": "GVL_HmiPanel.xUnsuspend", "icon": "play"},
                {
                    "label": "Clear",
                    "variable": "GVL_HmiPanel.xClear",
                    "icon": "reset",
                    "access": MAINT,
                },
            ],
        },
    ],
)

robot = page(
    "Robot",
    "Robot",
    "6-axis arm R-1, joint space",
    "machine",
    [
        *[
            {
                "type": "bar",
                "title": f"J{j}",
                "at": [j, 1, 1, 3],
                "value": f"GVL_Bridge.aJointPosSp[{j}]",
                "min": -180,
                "max": 180,
                "unit": "°",
                "decimals": 1,
            }
            for j in range(1, 7)
        ],
        *[
            {
                "type": "bar",
                "title": f"J{j} error",
                "at": [6 + j, 1, 1, 3],
                "value": f"GVL_Bridge.aFollowingError[{j}]",
                "min": 0,
                "max": 6,
                "unit": "°",
                "decimals": 2,
                "bands": [
                    {"from": 0, "tone": "accent"},
                    {"from": 2, "tone": "warn"},
                    {"from": 5, "tone": "alarm"},
                ],
            }
            for j in range(1, 7)
        ],
        *[
            {
                "type": "buttons",
                "title": title,
                "icon": "manual",
                "at": [col, 4, 3, 3],
                "items": [
                    item
                    for j in joints
                    for item in (
                        {
                            "label": f"J{j} -",
                            "variable": f"GVL_Hmi.axJogMinus[{j}]",
                            "mode": "tap",
                            "access": MAINT,
                        },
                        {
                            "label": f"J{j} +",
                            "variable": f"GVL_Hmi.axJogPlus[{j}]",
                            "mode": "tap",
                            "access": MAINT,
                        },
                    )
                ],
            }
            for title, col, joints in (
                ("Jog J1-J3 (Manual)", 1, (1, 2, 3)),
                ("Jog J4-J6 (Manual)", 4, (4, 5, 6)),
            )
        ],
        {
            "type": "status",
            "title": "Robot",
            "icon": "info",
            "at": [7, 4, 3, 3],
            "items": [
                {
                    "label": "Jog permitted",
                    "off": "Jog locked",
                    "on": "GVL_HmiView.xJogPermitted",
                    "tone": "accent",
                },
                {"label": "Robot moving", "off": "Robot at rest", "on": "GVL_HmiView.xRobotMoving"},
                {"label": "Vacuum on", "off": "Vacuum off", "on": "GVL_Bridge.xVacuumOn"},
                {
                    "label": "Following error warning",
                    "on": "GVL_HmiView.axAlarmActive[6]",
                    "tone": "warn",
                },
                {
                    "label": "Following error fault",
                    "on": "GVL_HmiView.axAlarmActive[7]",
                    "tone": "alarm",
                },
            ],
        },
        {
            "type": "setpoint",
            "title": "Speed override",
            "icon": "speed",
            "at": [10, 4, 3, 3],
            "variable": "GVL_Hmi.rOverride",
            "min": 0.1,
            "max": 1.0,
            "step": 0.1,
            "decimals": 1,
            "access": MAINT,
        },
        {
            "type": "value",
            "title": "Worst joint",
            "icon": "machine",
            "at": [1, 7, 3, 2],
            "value": "GVL_Bridge.iWorstJoint",
            "decimals": 0,
        },
        {
            "type": "value",
            "title": "Pick sequence",
            "icon": "process",
            "at": [4, 7, 3, 2],
            "value": "GVL_HmiView.sPickStep",
        },
        {
            "type": "trend",
            "title": "Following error",
            "icon": "trend",
            "at": [7, 7, 6, 2],
            "seconds": 120,
            "series": [
                {"value": f"GVL_Bridge.aFollowingError[{j}]", "label": f"J{j} °"}
                for j in range(1, 7)
            ],
        },
    ],
)

alarms = page(
    "Alarms",
    "Alarms",
    "ISA-18.2 priorities: P1 critical, P2 error, P3 warning",
    "alarm",
    [
        {
            "type": "status",
            "title": "P1 critical",
            "icon": "alarm",
            "at": [1, 1, 3, 5],
            "items": alarm_lamps((1, 2, 3, 4, 7, 8)),
        },
        {
            "type": "status",
            "title": "P2 error",
            "icon": "alarm",
            "at": [4, 1, 3, 5],
            "items": alarm_lamps((5, 9, 10, 16)),
        },
        {
            "type": "status",
            "title": "P3 warning",
            "icon": "warning",
            "at": [7, 1, 3, 5],
            "items": alarm_lamps((6, 11, 12, 13, 14, 15)),
        },
        {
            "type": "value",
            "title": "Newest alarm",
            "icon": "alarm",
            "at": [1, 6, 9, 3],
            "value": "GVL_HmiView.sNewestAlarm",
        },
        {
            "type": "buttons",
            "title": "Alarm handling",
            "at": [10, 1, 3, 3],
            "items": [
                {"label": "Acknowledge all", "variable": "GVL_HmiPanel.xAckAll", "icon": "check"},
                {
                    "label": "Clear",
                    "variable": "GVL_HmiPanel.xClear",
                    "icon": "reset",
                    "access": MAINT,
                },
                {
                    "label": "Abort",
                    "variable": "GVL_HmiPanel.xAbort",
                    "icon": "stop",
                    "access": MAINT,
                },
            ],
        },
        {
            "type": "status",
            "title": "Conditions present",
            "icon": "warning",
            "at": [10, 4, 3, 5],
            "items": [
                {"label": label, "on": f"GVL_HmiView.axAlarmActive[{i}]", "tone": tone}
                for i, label, tone in (
                    (1, "E-stop pressed", "alarm"),
                    (2, "Door open", "alarm"),
                    (3, "Bridge lost", "alarm"),
                    (4, "Axis group error", "alarm"),
                    (7, "Following error fault", "alarm"),
                    (8, "Feedback stale", "alarm"),
                    (10, "Vacuum lost", "alarm"),
                    (12, "Bin full", "warn"),
                )
            ],
        },
    ],
)

if __name__ == "__main__":
    for screen in (overview, robot, alarms):
        (HERE / f"{screen['name']}.json").write_text(
            json.dumps(screen, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print("written:", ", ".join(s["name"] for s in (overview, robot, alarms)))
