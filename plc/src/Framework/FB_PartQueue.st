(*
    FB_PartQueue
    Purpose : Fixed-capacity store of part records; a record with eState = Free is an empty slot.
    Methods : Add, FindIndex, Get, Put, Release; property Count
*)
FUNCTION_BLOCK FB_PartQueue
VAR
    aRecords : ARRAY[1..GVL_Config.MAX_PARTS] OF ST_PartRecord;
    stEmpty : ST_PartRecord;
END_VAR
