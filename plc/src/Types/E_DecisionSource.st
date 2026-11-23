// Where a part's quality decision came from.
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_DecisionSource :
(
    None := 0,
    Ai := 1,
    Fallback := 2
);
END_TYPE
