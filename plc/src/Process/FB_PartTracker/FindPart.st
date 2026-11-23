// Slot index of the part with this id, or 0.
METHOD FindPart : UINT
VAR_INPUT
    udiPartId : UDINT;
END_VAR

FindPart := fbQueue.FindIndex(udiPartId);
