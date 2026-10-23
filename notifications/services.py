from .models import AuditLog


def log_attendance_edit(user, attendance_id, old_status, new_status,
                        class_id=None, attendance_date=None):
    """Create one audit log entry for an attendance edit.

    Call this from the attendance edit code with the user who made the
    change, the record id, and the old and new status.
    """
    return AuditLog.objects.create(
        edited_by=user,
        attendance_id=attendance_id,
        class_id=class_id,
        attendance_date=attendance_date,
        old_status=old_status,
        new_status=new_status,
        details=f"Status changed from {old_status} to {new_status}",
    )
