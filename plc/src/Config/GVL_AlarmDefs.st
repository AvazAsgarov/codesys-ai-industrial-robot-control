// Alarm definitions: class and operator text for every E_AlarmId.
// Critical -> PackML Abort, Error -> Stop, Warning -> no state change (BinFull suspends the unit).
{attribute 'qualified_only'}
VAR_GLOBAL CONSTANT
    aDefs : ARRAY[E_AlarmId.None..E_AlarmId.QueueOverflow] OF ST_AlarmDef := [
        (eClass := E_AlarmClass.Info, sText := 'No alarm'),
        (eClass := E_AlarmClass.Critical, sText := 'Emergency stop pressed'),
        (eClass := E_AlarmClass.Critical, sText := 'Safety door opened in automatic mode'),
        (eClass := E_AlarmClass.Critical, sText := 'Connection to the digital twin bridge lost'),
        (eClass := E_AlarmClass.Critical, sText := 'Robot axis group error'),
        (eClass := E_AlarmClass.Error, sText := 'Conveyor axis error'),
        (eClass := E_AlarmClass.Warning, sText := 'Joint following error above warning limit'),
        (eClass := E_AlarmClass.Critical, sText := 'Joint following error above fault limit'),
        (eClass := E_AlarmClass.Critical, sText := 'Joint feedback not updated'),
        (eClass := E_AlarmClass.Error, sText := 'Vacuum not reached - part not gripped'),
        (eClass := E_AlarmClass.Error, sText := 'Vacuum lost while carrying a part'),
        (eClass := E_AlarmClass.Warning, sText := 'Part left the pick window unpicked'),
        (eClass := E_AlarmClass.Warning, sText := 'A bin is full - cell suspended until it is emptied'),
        (eClass := E_AlarmClass.Warning, sText := 'No vision result for a captured part'),
        (eClass := E_AlarmClass.Warning, sText := 'AI decision late - fallback rule used'),
        (eClass := E_AlarmClass.Warning, sText := 'Low detection confidence - part quarantined'),
        (eClass := E_AlarmClass.Error, sText := 'Part queue full')];
END_VAR
