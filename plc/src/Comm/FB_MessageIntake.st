(*
    FB_MessageIntake
    Purpose : Detects new bridge messages by their sequence number, so a message written twice
              (or re-read) is processed only once.
    Outputs : xVisionNew, xDecisionNew - TRUE for one cycle per new message
*)
FUNCTION_BLOCK FB_MessageIntake
VAR_INPUT
    stVision : ST_VisionMsg;
    stDecision : ST_DecisionMsg;
END_VAR
VAR_OUTPUT
    xVisionNew : BOOL;
    xDecisionNew : BOOL;
END_VAR
VAR
    udiLastVisionSeq : UDINT;
    udiLastDecisionSeq : UDINT;
END_VAR

xVisionNew := stVision.udiSeq <> udiLastVisionSeq;
udiLastVisionSeq := stVision.udiSeq;
xDecisionNew := stDecision.udiSeq <> udiLastDecisionSeq;
udiLastDecisionSeq := stDecision.udiSeq;
