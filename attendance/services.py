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

def get_daily_attendance(user, class_id, date_value):
    """REQ4.1: every student's status for one class on one date.

    Admins can view any class. A teacher can only view a class they are
    assigned to. If nothing was marked that day, `marked` is False and a
    clear message is returned instead of an error.
    """
    try:
        class_id = int(class_id)
    except (TypeError, ValueError):
        raise AttendanceError("classId is required and must be a number.", 400)

    academic_class = AcademicClass.objects.filter(pk=class_id).first()
    if academic_class is None:
        raise AttendanceError("Class not found.", 404)
    if user.role == User.Role.TEACHER and not is_class_teacher(user, academic_class):
        raise AttendanceError("You are not assigned to this class.", 403)

    date = parse_date(date_value)
    records = list(
        Attendance.objects.filter(academic_class=academic_class, date=date)
        .select_related("student")
        .order_by("student__roll_number")
    )

    counts = {status: 0 for status in VALID_STATUSES}
    for record in records:
        counts[record.status] += 1

    return {
        "classId": academic_class.pk,
        "className": str(academic_class),
        "date": date.isoformat(),
        "marked": bool(records),
        "message": "" if records else "Attendance has not been marked for this class on this date.",
        "counts": counts,
        "records": [
            {
                "attendanceId": r.pk,
                "studentId": r.student_id,
                "rollNumber": r.student.roll_number,
                "name": r.student.name,
                "status": r.status,
                "remarks": r.remarks,
            }
            for r in records
        ],
    }

# REQ4.2: which statuses count as "present" in the attendance percentage.
# Late counts, because the student was in school. Absent and Excused do not.
COUNTED_AS_PRESENT = ("Present", "Late")


def calculate_attendance_summary(statuses):
    """Days present / total school days, from a list of daily statuses."""
    total = len(statuses)
    present = sum(1 for status in statuses if status in COUNTED_AS_PRESENT)
    percentage = round(present * 100 / total, 1) if total else 0.0
    return {"totalDays": total, "presentDays": present, "percentage": percentage}


def can_view_student(user, student):
    """Admins see everyone, a teacher sees their own class, a parent sees their own child."""
    if user.role == User.Role.ADMIN:
        return True
    if user.role == User.Role.TEACHER:
        return bool(student.section_id) and is_class_teacher(
            user, student.section.academic_class
        )
    if user.role == User.Role.STUDENT_PARENT:
        return student.parent_id == user.pk
    return False


def get_student_history(user, student_id):
    """REQ4.2: every attendance record for one student, plus their percentage."""
    student = Student.objects.select_related("section__academic_class").filter(
        pk=student_id
    ).first()
    if student is None:
        raise AttendanceError("Student not found.", 404)
    if not can_view_student(user, student):
        raise AttendanceError("You are not allowed to view this student.", 403)

    records = list(Attendance.objects.filter(student=student).order_by("-date"))
    counts = {status: 0 for status in VALID_STATUSES}
    for record in records:
        counts[record.status] += 1

    return {
        "student": {
            "id": student.pk,
            "name": student.name,
            "rollNumber": student.roll_number,
            "className": student.student_class,
        },
        **calculate_attendance_summary([record.status for record in records]),
        "counts": counts,
        "records": [
            {"date": r.date.isoformat(), "status": r.status, "remarks": r.remarks}
            for r in records
        ],
    }