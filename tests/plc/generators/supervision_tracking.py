"""Generate tests/plc/joint_monitor.json and tests/plc/tracking.json.

Run: python tests/plc/generators/supervision_tracking.py tests/plc
All cases are time based (waitMs), so the application keeps running between steps.
"""

import json
import sys
from pathlib import Path

JM = "PRG_TestJointMonitor."
TR = "PRG_TestTracking."
QUALITY = {"Unknown": 0, "Ok": 1, "Rework": 2, "Scrap": 3}


def w(prefix, **values):
    return {"write": {prefix + k: v for k, v in values.items()}}


def e(prefix, **values):
    return {"expect": {prefix + k: v for k, v in values.items()}}


def wait(ms):
    return {"waitMs": ms}


def near(value, tol=0.01):
    return {"op": "=", "value": value, "tolerance": tol}


# --- joint monitor ------------------------------------------------------------------------
jm_cases = [
    {
        "name": "loopback_never_faults",
        "steps": [
            w(JM, xReinit=True),
            wait(200),
            w(
                JM,
                **{
                    "fbMon.xLoopback": True,
                    "fbMon.xActive": True,
                    "fbMon.aSetpoint[1]": 50.0,
                    "fbMon.aFeedback[1]": 0.0,
                },
            ),
            wait(400),
            e(JM, **{"fbMon.xWarn": False, "fbMon.xFault": False, "fbMon.xStale": False}),
        ],
    },
    {
        "name": "warn_threshold",
        "steps": [
            w(JM, xReinit=True),
            wait(200),
            w(
                JM,
                xAutoSeq=True,
                **{
                    "fbMon.xLoopback": False,
                    "fbMon.xActive": True,
                    "fbMon.aSetpoint[2]": 10.0,
                    "fbMon.aFeedback[2]": 7.0,
                },
            ),
            wait(300),
            e(JM, **{"fbMon.xWarn": True, "fbMon.xFault": False, "fbMon.iWorstJoint": 2}),
        ],
    },
    {
        "name": "fault_threshold_and_worst_joint",
        "steps": [
            w(
                JM,
                **{
                    "fbMon.aFeedback[2]": 10.0,
                    "fbMon.aSetpoint[4]": 20.0,
                    "fbMon.aFeedback[4]": 12.0,
                },
            ),
            wait(300),
            e(
                JM,
                **{
                    "fbMon.xFault": True,
                    "fbMon.iWorstJoint": 4,
                    "fbMon.aFollowingError[4]": near(8.0),
                    "fbAlarms.xCriticalActive": True,
                },
            ),
        ],
    },
    {
        "name": "stale_feedback_faults",
        "steps": [
            w(JM, xReinit=True),
            wait(200),
            w(JM, xAutoSeq=False, **{"fbMon.xLoopback": False, "fbMon.xActive": True}),
            wait(1000),
            e(JM, **{"fbMon.xStale": True, "fbMon.xFault": True}),
        ],
    },
    {
        "name": "inactive_no_stale_check",
        "steps": [
            w(JM, xReinit=True),
            wait(200),
            w(JM, xAutoSeq=False, **{"fbMon.xLoopback": False, "fbMon.xActive": False}),
            wait(1000),
            e(JM, **{"fbMon.xStale": False, "fbMon.xFault": False}),
        ],
    },
    {
        # feedback that answers an older setpoint sample is compared with that sample
        "name": "lagged_feedback_no_fault",
        "steps": [
            w(JM, xReinit=True),
            wait(200),
            w(
                JM,
                iLag=10,
                xFreeze=False,
                xRamp=True,
                xAutoSeq=True,
                **{"fbMon.xLoopback": False, "fbMon.xActive": True},
            ),
            wait(1500),
            e(
                JM,
                lrRampSpeed={"op": ">", "value": 50},
                **{
                    "fbMon.xWarn": False,
                    "fbMon.xFault": False,
                    "fbMon.aFollowingError[1]": {"op": "<", "value": 0.5},
                },
            ),
            w(JM, xRamp=False),
            wait(200),
        ],
    },
    {
        "name": "blocked_joint_faults",
        "steps": [
            w(JM, xReinit=True),
            wait(200),
            w(
                JM,
                iLag=10,
                xFreeze=True,
                xRamp=True,
                xAutoSeq=True,
                **{"fbMon.xLoopback": False, "fbMon.xActive": True},
            ),
            wait(1500),
            e(
                JM,
                **{
                    "fbMon.xFault": True,
                    "fbMon.iWorstJoint": 1,
                    "fbAlarms.xCriticalActive": True,
                },
            ),
            w(JM, xRamp=False, xFreeze=False),
            wait(200),
        ],
    },
    {
        # OPC UA may hand the task new positions before their sequence number (a torn write):
        # one bad sample must not abort the cell; a persisting error still does (blocked joint)
        "name": "torn_sample_no_fault",
        "steps": [
            w(JM, xReinit=True),
            wait(200),
            w(
                JM,
                iLag=10,
                xFreeze=False,
                xRamp=True,
                xAutoSeq=True,
                **{"fbMon.xLoopback": False, "fbMon.xActive": True},
            ),
            wait(500),
            w(JM, iTornSamples=1),
            wait(300),
            e(
                JM,
                iTornSamples=0,
                **{"fbMon.xFault": False, "fbAlarms.xCriticalActive": False},
            ),
            w(JM, xRamp=False),
            wait(200),
        ],
    },
]


# --- tracking -------------------------------------------------------------------------------
def capture():
    return [w(TR, xTriggerPE1=True), wait(200)]


def vision(part_id, cls, conf, x=300.0, valid=True):
    return [
        w(
            TR,
            **{
                "stVisIn.udiPartId": part_id,
                "stVisIn.xValid": valid,
                "stVisIn.usiClass": cls,
                "stVisIn.rConfidence": conf,
                "stVisIn.lrX": x,
                "stVisIn.lrY": 0.0,
                "stVisIn.lrTheta": 15.0,
            },
            xSendVision=True,
        ),
        wait(200),
    ]


def decision(part_id, quality, reliable=True):
    return [
        w(
            TR,
            **{
                "stDecIn.udiPartId": part_id,
                "stDecIn.eQuality": QUALITY[quality],
                "stDecIn.rQualityProb": 0.95,
                "stDecIn.xIdentReliable": reliable,
            },
            xSendDecision=True,
        ),
        wait(200),
    ]


def query(part_id, **expected):
    return [
        w(TR, udiQueryId=part_id),
        wait(150),
        e(TR, **{"stRec." + k: v for k, v in expected.items()}),
    ]


tr_cases = [
    {
        "name": "capture_creates_record",
        "steps": [
            w(TR, xReinit=True, lrBeltPos=0.0),
            wait(200),
            *capture(),
            e(
                TR,
                uiCount=1,
                **{"fbTracker.stCapture.udiSeq": 1, "fbTracker.stCapture.udiPartId": 1},
            ),
        ],
    },
    {
        "name": "vision_then_decision_sets_bin",
        "steps": [
            *vision(1, 1, 0.9),
            *decision(1, "Ok"),
            *query(
                1,
                eState="E_PartState.Decided",
                eTargetBin="E_Bin.TypeB",
                eDecisionSource="E_DecisionSource.Ai",
            ),
        ],
    },
    {
        "name": "scrap_goes_to_scrap",
        "steps": [
            *capture(),
            *vision(2, 0, 0.9),
            *decision(2, "Scrap"),
            *query(2, eTargetBin="E_Bin.Scrap"),
        ],
    },
    {
        "name": "low_confidence_quarantine",
        "steps": [
            *capture(),
            *vision(3, 0, 0.3),
            *decision(3, "Ok"),
            *query(3, eTargetBin="E_Bin.Quarantine"),
        ],
    },
    {
        "name": "duplicate_result_ignored",
        "steps": [
            *capture(),
            *vision(4, 2, 0.9),
            w(TR, **{"stVisIn.usiClass": 0}, xResendVision=True),
            wait(200),
            *query(4, usiClass=2),
            e(TR, **{"fbTracker.udiVisionMsgs": 4}),
        ],
    },
    {
        "name": "unknown_part_result_ignored",
        "steps": [
            *vision(99, 0, 0.9),
            w(TR, udiQueryId=99),
            wait(150),
            e(TR, xQueryFound=False, uiCount=4),
        ],
    },
    {
        "name": "deadline_uses_fallback",
        "steps": [
            *capture(),
            *vision(5, 2, 0.9),
            wait(3000),
            *query(
                5,
                eState="E_PartState.Decided",
                eTargetBin="E_Bin.TypeC",
                eDecisionSource="E_DecisionSource.Fallback",
            ),
            e(TR, **{"fbAlarms.eNewest": "E_AlarmId.DecisionFallback"}),
        ],
    },
    {
        "name": "no_vision_goes_to_quarantine",
        "steps": [
            *capture(),
            wait(3000),
            *query(6, eTargetBin="E_Bin.Quarantine", eDecisionSource="E_DecisionSource.Fallback"),
        ],
    },
    {
        "name": "missed_part_is_skipped",
        "steps": [
            w(TR, xReinit=True, lrBeltPos=0.0),
            wait(200),
            *capture(),
            *vision(1, 0, 0.9, x=300.0),
            *decision(1, "Ok"),
            w(TR, lrBeltPos=1000.0),
            wait(200),
            e(TR, uiNext=1),
            w(TR, lrBeltPos=1500.0),
            wait(200),
            e(
                TR,
                uiNext=0,
                uiCount=0,
                **{"fbTracker.udiMissed": 1, "fbAlarms.eNewest": "E_AlarmId.PartMissed"},
            ),
        ],
    },
    {
        "name": "queue_overflow_alarm",
        "steps": [
            w(TR, xReinit=True, lrBeltPos=0.0),
            wait(200),
            w(TR, uiFillCount=33),
            wait(1500),
            e(TR, uiCount=32, **{"fbAlarms.xErrorActive": True}),
            # parts leave the window -> slots free; the next capture clears the overflow
            w(TR, lrBeltPos=5000.0),
            wait(300),
            e(TR, uiCount=0),
            *capture(),
            w(TR, xAck=True),
            wait(300),
            e(TR, uiCount=1, **{"fbAlarms.xErrorActive": False}),
        ],
    },
    {
        # PackML Resetting forgets the tracked parts (the belt may have been cleared by hand)
        "name": "clear_forgets_all_parts",
        "steps": [
            w(TR, xReinit=True, lrBeltPos=0.0),
            wait(200),
            *capture(),
            *capture(),
            e(TR, uiCount=2, **{"fbTracker.stCapture.udiPartId": 2}),
            w(TR, xClear=True),
            wait(200),
            e(TR, uiCount=0),
            *capture(),
            # part ids keep counting: a late message for an old part matches nothing
            e(TR, uiCount=1, **{"fbTracker.stCapture.udiPartId": 3}),
        ],
    },
]

out = Path(sys.argv[1])
for name, cases in (("joint_monitor.json", jm_cases), ("tracking.json", tr_cases)):
    with (out / name).open("w", encoding="utf-8", newline="\n") as f:
        json.dump({"cases": cases}, f, indent=2)
        f.write("\n")
    print(name, len(cases), "cases")
