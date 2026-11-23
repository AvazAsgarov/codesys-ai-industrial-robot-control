// Output bins: one per good part type, then the quality bins.
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_Bin :
(
    TypeA := 0,
    TypeB := 1,
    TypeC := 2,
    Rework := 3,
    Scrap := 4,
    Quarantine := 5
);
END_TYPE
