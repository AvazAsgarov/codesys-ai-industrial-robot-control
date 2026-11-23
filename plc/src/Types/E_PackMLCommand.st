// PackML state commands.
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_PackMLCommand :
(
    None := 0,
    Reset := 1,
    Start := 2,
    Stop := 3,
    Hold := 4,
    Unhold := 5,
    Suspend := 6,
    Unsuspend := 7,
    Abort := 8,
    Clear := 9,
    Complete := 10
);
END_TYPE
