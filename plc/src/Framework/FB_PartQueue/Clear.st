// Empty every slot.
METHOD Clear
VAR
    i : UINT;
END_VAR

FOR i := 1 TO GVL_Config.MAX_PARTS DO
    aRecords[i] := stEmpty;
END_FOR
