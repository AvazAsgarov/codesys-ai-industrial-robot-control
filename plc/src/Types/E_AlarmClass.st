// Alarm classes (ISA-18.2 style priorities). Critical -> Abort, Error -> Stop.
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_AlarmClass :
(
    Info := 0,
    Warning := 1,
    Error := 2,
    Critical := 3
);
END_TYPE
