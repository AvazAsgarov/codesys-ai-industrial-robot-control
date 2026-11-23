// Quality decision written by the bridge (THX-02). A new message has a new udiSeq.
TYPE ST_DecisionMsg :
STRUCT
    udiSeq : UDINT;
    udiPartId : UDINT;
    eQuality : E_Quality;
    rQualityProb : REAL;
    xIdentReliable : BOOL;
END_STRUCT
END_TYPE
