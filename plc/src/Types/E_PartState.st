// Life cycle of a tracked part.
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_PartState :
(
    Free := 0,
    Captured := 1,
    Identified := 2,
    Decided := 3,
    Scheduled := 4,
    Picked := 5,
    Placed := 6,
    Missed := 7,
    Dropped := 8
);
END_TYPE
