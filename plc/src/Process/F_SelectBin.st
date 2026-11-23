(*
    F_SelectBin
    Purpose : Bin selection of spec section 7.2:
              1. no valid vision, low confidence, or an AI decision saying the identification
                 is unreliable -> Quarantine
              2. quality Scrap -> Scrap, quality Rework -> Rework
              3. otherwise the type bin of the detected class
*)
FUNCTION F_SelectBin : E_Bin
VAR_INPUT
    stRec : ST_PartRecord;
    rConfThreshold : REAL;
    aClassToBin : ARRAY[0..2] OF E_Bin;
END_VAR

IF NOT stRec.xVisionValid OR stRec.rConfidence < rConfThreshold THEN
    F_SelectBin := E_Bin.Quarantine;
ELSIF stRec.eDecisionSource = E_DecisionSource.Ai AND NOT stRec.xIdentReliable THEN
    F_SelectBin := E_Bin.Quarantine;
ELSIF stRec.eQuality = E_Quality.Scrap THEN
    F_SelectBin := E_Bin.Scrap;
ELSIF stRec.eQuality = E_Quality.Rework THEN
    F_SelectBin := E_Bin.Rework;
ELSIF stRec.usiClass <= 2 THEN
    F_SelectBin := aClassToBin[stRec.usiClass];
ELSE
    F_SelectBin := E_Bin.Quarantine;
END_IF
