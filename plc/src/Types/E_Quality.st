// Quality disposition of a part (spec section 6.3).
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_Quality :
(
    Unknown := 0,
    Ok := 1,
    Rework := 2,
    Scrap := 3
);
END_TYPE
