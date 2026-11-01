import datetime
import logging
import time

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import AuditLog, Notification, NotificationAttempt

logger = logging.getLogger("sams.notifications")

# REQ5.1: only an unexcused absence triggers a parent email.
NOTIFY_STATUSES = ("Absent",)

# REQ5.4: each notification is tried at most this many times.
MAX_SEND_ATTEMPTS = 3


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


def _parent_email(student):
    parent = student.parent
    return (parent.email or "").strip() if parent else ""


def _build_message(attendance):
    student = attendance.student
    subject = f"Absence notice: {student.name} on {attendance.date:%d %b %Y}"
    message = (
        "Dear Parent/Guardian,\n\n"
        f"{student.name} (roll no. {student.roll_number}) was marked Absent "
        f"in {attendance.academic_class} on {attendance.date:%A, %d %B %Y}.\n\n"
        "If this absence should be excused, please contact the school.\n\n"
        "This is an automated message from SAMS."
    )
    return subject, message


def _try_send(notification):
    send_mail(
        notification.subject,
        notification.message,
        settings.DEFAULT_FROM_EMAIL,
        [notification.recipient_email],
        fail_silently=False,
    )


def send_notification(notification, max_attempts=None, retry_delay=None):
    """Send one notification email, retrying on failure (REQ5.4).

    Each attempt is saved as a NotificationAttempt and failures are written
    to the application log. After the last failed attempt the notification
    status is set to failed.
    """
    if max_attempts is None:
        max_attempts = getattr(settings, "SAMS_NOTIFICATION_MAX_ATTEMPTS", MAX_SEND_ATTEMPTS)
    if retry_delay is None:
        retry_delay = getattr(settings, "SAMS_NOTIFICATION_RETRY_DELAY", 0)

    while notification.attempts < max_attempts:
        notification.attempts += 1
        attempt_number = notification.attempts
        try:
            _try_send(notification)
        except Exception as exc:  # any backend error (SMTP, network, ...)
            error = f"{type(exc).__name__}: {exc}"[:255]
            NotificationAttempt.objects.create(
                notification=notification,
                attempt_number=attempt_number,
                succeeded=False,
                error=error,
            )
            notification.last_error = error
            is_last = attempt_number >= max_attempts
            notification.status = (
                Notification.Status.FAILED if is_last else Notification.Status.PENDING
            )
            notification.save(update_fields=["attempts", "status", "last_error"])
            logger.warning(
                "Notification send failed notification_id=%s student_id=%s attempt=%s/%s error=%s",
                notification.pk,
                notification.student_id,
                attempt_number,
                max_attempts,
                type(exc).__name__,
            )
            if not is_last and retry_delay:
                time.sleep(retry_delay)
            continue

        NotificationAttempt.objects.create(
            notification=notification,
            attempt_number=attempt_number,
            succeeded=True,
        )
        notification.status = Notification.Status.SENT
        notification.sent_at = timezone.now()
        notification.last_error = ""
        notification.save(update_fields=["attempts", "status", "sent_at", "last_error"])
        logger.info(
            "Notification sent notification_id=%s student_id=%s attempt=%s",
            notification.pk,
            notification.student_id,
            attempt_number,
        )
        return notification

    if notification.status != Notification.Status.FAILED:
        notification.status = Notification.Status.FAILED
        notification.save(update_fields=["status"])
    logger.error(
        "Notification marked failed after %s attempts notification_id=%s student_id=%s",
        notification.attempts,
        notification.pk,
        notification.student_id,
    )
    return notification


def notify_absence(attendance):
    """REQ5.1: email the parent when a student is marked Absent.

    Returns the saved Notification, or None for Present, Late, and Excused.
    A record is saved even if the parent has no email address, so the
    school can see who could not be reached.
    """
    if attendance.status not in NOTIFY_STATUSES:
        return None

    subject, message = _build_message(attendance)
    recipient = _parent_email(attendance.student)
    notification = Notification.objects.create(
        student=attendance.student,
        attendance=attendance,
        recipient_email=recipient,
        subject=subject,
        message=message,
        status=Notification.Status.PENDING if recipient else Notification.Status.SKIPPED,
    )
    if not recipient:
        logger.info(
            "Notification skipped, no parent email notification_id=%s student_id=%s",
            notification.pk,
            attendance.student_id,
        )
        return notification
    return send_notification(notification)


def notify_absences(attendance_records):
    """Send absence emails for a batch of saved attendance records."""
    return [
        notification
        for notification in (notify_absence(record) for record in attendance_records)
        if notification is not None
    ]


class AuditLogFilterError(ValueError):
    """A filter value on the audit log search could not be understood."""


def _parse_id(value, name):
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise AuditLogFilterError(f"{name} must be a number.")
    if parsed <= 0:
        raise AuditLogFilterError(f"{name} must be a positive number.")
    return parsed


def _parse_date(value, name):
    if value in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise AuditLogFilterError(f"{name} must be in YYYY-MM-DD format.")


def search_audit_log(class_id=None, date=None, user_id=None):
    """REQ5.3: audit log entries filtered by class, attendance date, and/or editor.

    Filters are optional and combine with AND. `date` matches the date of the
    attendance record that was changed.
    """
    class_id = _parse_id(class_id, "classId")
    user_id = _parse_id(user_id, "userId")
    date = _parse_date(date, "date")

    entries = AuditLog.objects.select_related("edited_by")
    if class_id is not None:
        entries = entries.filter(class_id=class_id)
    if date is not None:
        entries = entries.filter(attendance_date=date)
    if user_id is not None:
        entries = entries.filter(edited_by_id=user_id)
    return entries.order_by("-edited_at", "-pk")


def describe_audit_entries(entries):
    """Attach class and student names to a page of audit entries (2 extra queries)."""
    from attendance.models import Attendance
    from students.models import AcademicClass

    entries = list(entries)
    class_names = {
        pk: str(c)
        for pk, c in AcademicClass.objects.in_bulk(
            {e.class_id for e in entries if e.class_id}
        ).items()
    }
    students = {
        a.pk: a.student
        for a in Attendance.objects.select_related("student").filter(
            pk__in={e.attendance_id for e in entries if e.attendance_id}
        )
    }
    for entry in entries:
        entry.class_name = class_names.get(entry.class_id, "")
        student = students.get(entry.attendance_id)
        entry.student_name = student.name if student else ""
    return entries


def audit_entry_to_dict(entry):
    return {
        "id": entry.pk,
        "editedAt": entry.edited_at.isoformat(),
        "editedBy": entry.edited_by.username if entry.edited_by else None,
        "editedById": entry.edited_by_id,
        "attendanceId": entry.attendance_id,
        "classId": entry.class_id,
        "className": getattr(entry, "class_name", ""),
        "studentName": getattr(entry, "student_name", ""),
        "attendanceDate": entry.attendance_date.isoformat() if entry.attendance_date else None,
        "oldStatus": entry.old_status,
        "newStatus": entry.new_status,
        "details": entry.details,
    }
