// Forget every tracked part (PackML Resetting: the parts on the belt are unknown, e.g. removed
// by hand while the cell was stopped). Part ids keep counting, so a late vision or decision
// message for a forgotten part matches nothing.
METHOD Clear

fbQueue.Clear();
