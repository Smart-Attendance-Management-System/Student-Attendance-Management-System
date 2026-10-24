"""Business rules for marking and editing attendance."""

import datetime

from django.db import IntegrityError, transaction

from accounts.models import User
from notifications.services import log_attendance_edit
from students.models import AcademicClass, Student

from .models import Attendance

VALID_STATUSES = [choice for choice, _ in Attendance.Status.choices]


class AttendanceError(Exception):
    """A problem with an attendance request, with the HTTP status to return."""

    def __init__(self, message, status_code):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def is_valid_status(status):
    return status in VALID_STATUSES


def is_class_teacher(user, academic_class):
    """Only the teacher assigned to the class may mark or edit its attendance."""
    return (
        user.role == User.Role.TEACHER
        and academic_class.class_teacher_id == user.id
    )


def attendance_exists(academic_class, date):
    """REQ3.4: True if attendance was already marked for this class and date."""
    return Attendance.objects.filter(academic_class=academic_class, date=date).exists()


def parse_date(value):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise AttendanceError("Date must be in YYYY-MM-DD format.", 400)


def mark_attendance(teacher, class_id, date_value, records):
    """Save attendance for a whole class in one go.

    REQ3.2: any student in the class who is not in `records` is marked Present,
    so the teacher only needs to send the exceptions.
    """
    academic_class = AcademicClass.objects.filter(pk=class_id).first()
    if academic_class is None:
        raise AttendanceError("Class not found.", 400)
    if not is_class_teacher(teacher, academic_class):
        raise AttendanceError("You are not assigned to this class.", 403)

    date = parse_date(date_value)
    if not isinstance(records, list):
        raise AttendanceError("Records must be a list.", 400)

    students = {s.pk: s for s in Student.objects.filter(section__academic_class=academic_class)}
    if not students:
        raise AttendanceError("This class has no students.", 400)

    statuses = {}
    for record in records:
        student_id = record.get("studentId") if isinstance(record, dict) else None
        status = record.get("status") if isinstance(record, dict) else None
        if student_id not in students:
            raise AttendanceError(f"Student {student_id} is not in this class.", 400)
        if not is_valid_status(status):
            raise AttendanceError(f"Invalid status: {status}.", 400)
        statuses[student_id] = (status, (record.get("remarks") or "")[:255])

    if attendance_exists(academic_class, date):
        raise AttendanceError("Attendance already marked for this class and date.", 409)

    entries = [
        Attendance(
            student=student,
            academic_class=academic_class,
            date=date,
            status=statuses.get(student_id, (Attendance.Status.PRESENT, ""))[0],
            remarks=statuses.get(student_id, ("", ""))[1],
            marked_by=teacher,
        )
        for student_id, student in students.items()
    ]
    try:
        with transaction.atomic():
            Attendance.objects.bulk_create(entries)
    except IntegrityError:
        # Two submissions at the same moment: the database blocks the second one
        raise AttendanceError("Attendance already marked for this class and date.", 409)
    return entries


def edit_attendance(user, attendance, new_status, remarks=None):
    """Change one student's status and record the change in the audit log."""
    if not is_class_teacher(user, attendance.academic_class):
        raise AttendanceError("You are not assigned to this class.", 403)
    if not is_valid_status(new_status):
        raise AttendanceError(f"Invalid status: {new_status}.", 400)

    old_status = attendance.status
    attendance.status = new_status
    if remarks is not None:
        attendance.remarks = remarks[:255]
    attendance.save()  # updated_at changes automatically (REQ3.3)

    log_attendance_edit(
        user,
        attendance.pk,
        old_status,
        new_status,
        class_id=attendance.academic_class_id,
        attendance_date=attendance.date,
    )
    return attendance