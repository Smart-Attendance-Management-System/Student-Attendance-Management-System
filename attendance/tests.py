import datetime
import json
import time

from unittest.mock import patch
from django.db import IntegrityError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from notifications.models import AuditLog
from students.models import AcademicClass, Section, Student

from . import services
from .models import Attendance

TODAY = "2026-10-23"


class AttendanceTestBase(TestCase):
    """Shared setup: one class with 3 students, its teacher, and another teacher."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher1", password="pass12345", role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username="teacher2", password="pass12345", role=User.Role.TEACHER
        )
        self.admin = User.objects.create_user(
            username="admin1", password="pass12345", role=User.Role.ADMIN
        )
        self.cls = AcademicClass.objects.create(name="Grade 10", class_teacher=self.teacher)
        section = Section.objects.create(academic_class=self.cls, name="A")
        self.students = [
            Student.objects.create(
                name=f"Student {n}",
                student_class="Grade 10",
                roll_number=n,
                contact_details=f"parent{n}@example.com",
                section=section,
            )
            for n in (1, 2, 3)
        ]

    def post_json(self, url, payload):
        return self.client.post(url, json.dumps(payload), content_type="application/json")

    def mark_payload(self, records=None, date=TODAY):
        if records is None:
            records = [{"studentId": s.pk, "status": "Present"} for s in self.students]
        return {"classId": self.cls.pk, "date": date, "records": records}


# Unit tests

class AttendanceServiceUnitTests(AttendanceTestBase):
    def test_valid_statuses_are_accepted(self):
        for status in ("Present", "Absent", "Late", "Excused"):
            self.assertTrue(services.is_valid_status(status))

    def test_invalid_status_is_rejected(self):
        self.assertFalse(services.is_valid_status("Sick"))
        self.assertFalse(services.is_valid_status(""))

    def test_duplicate_check_false_before_marking(self):
        self.assertFalse(services.attendance_exists(self.cls, datetime.date(2026, 10, 23)))

    def test_duplicate_check_true_after_marking(self):
        services.mark_attendance(self.teacher, self.cls.pk, TODAY, [])
        self.assertTrue(services.attendance_exists(self.cls, datetime.date(2026, 10, 23)))

    def test_only_assigned_teacher_counts_as_class_teacher(self):
        self.assertTrue(services.is_class_teacher(self.teacher, self.cls))
        self.assertFalse(services.is_class_teacher(self.other_teacher, self.cls))
        self.assertFalse(services.is_class_teacher(self.admin, self.cls))

    def test_timestamp_set_on_save_and_updated_on_edit(self):
        entries = services.mark_attendance(self.teacher, self.cls.pk, TODAY, [])
        record = Attendance.objects.get(pk=entries[0].pk)
        first_update = record.updated_at
        self.assertIsNotNone(record.created_at)
        services.edit_attendance(self.teacher, record, "Late")
        record.refresh_from_db()
        self.assertGreater(record.updated_at, first_update)

    def test_database_blocks_duplicate_rows(self):
        Attendance.objects.create(
            student=self.students[0], academic_class=self.cls,
            date=datetime.date(2026, 10, 23), status="Present", marked_by=self.teacher,
        )
        with self.assertRaises(IntegrityError):
            Attendance.objects.create(
                student=self.students[0], academic_class=self.cls,
                date=datetime.date(2026, 10, 23), status="Absent", marked_by=self.teacher,
            )


# Integration tests:

class MarkAttendanceApiTests(AttendanceTestBase):
    url = "/api/attendance"

    def test_teacher_marks_whole_class(self):  
        self.client.force_login(self.teacher)
        response = self.post_json(self.url, self.mark_payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["savedCount"], 3)
        self.assertEqual(Attendance.objects.count(), 3)

    def test_all_four_statuses_are_saved(self):
        self.client.force_login(self.teacher)
        records = [
            {"studentId": self.students[0].pk, "status": "Absent"},
            {"studentId": self.students[1].pk, "status": "Late"},
            {"studentId": self.students[2].pk, "status": "Excused", "remarks": "Doctor"},
        ]
        self.post_json(self.url, self.mark_payload(records))
        saved = {a.student_id: a.status for a in Attendance.objects.all()}
        self.assertEqual(saved[self.students[0].pk], "Absent")
        self.assertEqual(saved[self.students[1].pk], "Late")
        self.assertEqual(saved[self.students[2].pk], "Excused")
        self.assertEqual(Attendance.objects.get(student=self.students[2]).remarks, "Doctor")

    def test_mark_all_present_with_exceptions(self):  
        self.client.force_login(self.teacher)
        records = [{"studentId": self.students[1].pk, "status": "Absent"}]
        response = self.post_json(self.url, self.mark_payload(records))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Attendance.objects.filter(status="Present").count(), 2)
        self.assertEqual(Attendance.objects.get(student=self.students[1]).status, "Absent")

    def test_marking_twice_returns_409(self):  
        self.client.force_login(self.teacher)
        self.post_json(self.url, self.mark_payload())
        response = self.post_json(self.url, self.mark_payload())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Attendance.objects.count(), 3)

    def test_same_class_on_different_date_is_allowed(self):
        self.client.force_login(self.teacher)
        self.post_json(self.url, self.mark_payload(date="2026-10-22"))
        response = self.post_json(self.url, self.mark_payload(date="2026-10-23"))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Attendance.objects.count(), 6)

    def test_wrong_teacher_gets_403(self):
        self.client.force_login(self.other_teacher)
        response = self.post_json(self.url, self.mark_payload())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_admin_cannot_mark_attendance(self):
        self.client.force_login(self.admin)
        response = self.post_json(self.url, self.mark_payload())
        self.assertEqual(response.status_code, 403)

    def test_invalid_status_gets_400(self):
        self.client.force_login(self.teacher)
        records = [{"studentId": self.students[0].pk, "status": "Sick"}]
        response = self.post_json(self.url, self.mark_payload(records))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_student_from_another_class_gets_400(self):
        other_cls = AcademicClass.objects.create(name="Grade 9", class_teacher=self.teacher)
        other_section = Section.objects.create(academic_class=other_cls, name="B")
        outsider = Student.objects.create(
            name="Outsider", student_class="Grade 9", roll_number=99,
            contact_details="x@example.com", section=other_section,
        )
        self.client.force_login(self.teacher)
        records = [{"studentId": outsider.pk, "status": "Present"}]
        response = self.post_json(self.url, self.mark_payload(records))
        self.assertEqual(response.status_code, 400)

    def test_bad_date_gets_400(self):
        self.client.force_login(self.teacher)
        response = self.post_json(self.url, self.mark_payload(date="23-10-2026"))
        self.assertEqual(response.status_code, 400)

    def test_missing_fields_get_400(self):
        self.client.force_login(self.teacher)
        response = self.post_json(self.url, {"records": []})
        self.assertEqual(response.status_code, 400)

    def test_class_with_no_students_gets_400(self):
        empty = AcademicClass.objects.create(name="Empty", class_teacher=self.teacher)
        self.client.force_login(self.teacher)
        response = self.post_json(self.url, {"classId": empty.pk, "date": TODAY, "records": []})
        self.assertEqual(response.status_code, 400)

    def test_not_logged_in_gets_401(self):
        response = self.post_json(self.url, self.mark_payload())
        self.assertEqual(response.status_code, 401)


class EditAttendanceApiTests(AttendanceTestBase):
    def setUp(self):
        super().setUp()
        services.mark_attendance(self.teacher, self.cls.pk, TODAY, [])
        self.record = Attendance.objects.get(student=self.students[0])

    def edit_url(self):
        return reverse("attendance:edit", args=[self.record.pk])

    def test_teacher_edits_status_and_audit_log_is_created(self):  
        self.client.force_login(self.teacher)
        response = self.post_json(self.edit_url(), {"status": "Absent"})
        self.assertEqual(response.status_code, 200)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "Absent")
        log = AuditLog.objects.get()
        self.assertEqual(log.edited_by, self.teacher)
        self.assertEqual((log.old_status, log.new_status), ("Present", "Absent"))

    def test_wrong_teacher_cannot_edit(self):
        self.client.force_login(self.other_teacher)
        response = self.post_json(self.edit_url(), {"status": "Absent"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_invalid_status_on_edit_gets_400(self):
        self.client.force_login(self.teacher)
        response = self.post_json(self.edit_url(), {"status": "Gone"})
        self.assertEqual(response.status_code, 400)

    def test_editing_missing_record_gets_404(self):
        self.client.force_login(self.teacher)
        response = self.post_json(reverse("attendance:edit", args=[9999]), {"status": "Absent"})
        self.assertEqual(response.status_code, 404)

class DailyAttendanceApiTests(AttendanceTestBase):
    """REQ4.1: daily attendance view for a class and date."""

    url = "/api/attendance/daily"

    def mark_with_exceptions(self, date=TODAY):
        records = [
            {"studentId": self.students[1].pk, "status": "Absent"},
            {"studentId": self.students[2].pk, "status": "Late", "remarks": "Bus"},
        ]
        services.mark_attendance(self.teacher, self.cls.pk, date, records)

    def get_daily(self, class_id=None, date=TODAY):
        params = {"classId": self.cls.pk if class_id is None else class_id, "date": date}
        return self.client.get(self.url, params)

    def test_teacher_sees_every_student_status_for_a_marked_day(self):
        self.mark_with_exceptions()
        self.client.force_login(self.teacher)
        response = self.get_daily()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["marked"])
        self.assertEqual(body["className"], "Grade 10")
        self.assertEqual(
            [(r["rollNumber"], r["status"]) for r in body["records"]],
            [(1, "Present"), (2, "Absent"), (3, "Late")],
        )
        self.assertEqual(body["records"][2]["remarks"], "Bus")
        self.assertEqual(
            body["counts"], {"Present": 1, "Absent": 1, "Late": 1, "Excused": 0}
        )

    def test_day_with_no_attendance_returns_clear_message(self):
        self.client.force_login(self.teacher)
        response = self.get_daily()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["marked"])
        self.assertEqual(body["records"], [])
        self.assertIn("not been marked", body["message"])

    def test_only_the_requested_date_is_returned(self):
        self.mark_with_exceptions(date="2026-10-22")
        self.client.force_login(self.teacher)
        body = self.get_daily(date=TODAY).json()
        self.assertFalse(body["marked"])
        self.assertTrue(self.get_daily(date="2026-10-22").json()["marked"])

    def test_admin_can_view_any_class(self):
        self.mark_with_exceptions()
        self.client.force_login(self.admin)
        response = self.get_daily()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["records"]), 3)

    def test_other_teacher_gets_403(self):
        self.mark_with_exceptions()
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.get_daily().status_code, 403)

    def test_student_parent_gets_403(self):
        parent = User.objects.create_user(
            username="parent1", password="pass12345", role=User.Role.STUDENT_PARENT
        )
        self.client.force_login(parent)
        self.assertEqual(self.get_daily().status_code, 403)

    def test_not_logged_in_is_refused(self):
        self.assertIn(self.get_daily().status_code, (401, 403))

    def test_bad_input_gets_400_or_404(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.get_daily(date="23-10-2026").status_code, 400)
        self.assertEqual(self.client.get(self.url, {"date": TODAY}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"classId": self.cls.pk}).status_code, 400)
        self.assertEqual(self.get_daily(class_id="abc").status_code, 400)
        self.assertEqual(self.get_daily(class_id=9999).status_code, 404)

class FiftyStudentSubmissionTests(AttendanceTestBase):
    """REQ3.5: a full class of 50 students is saved in one request, in under 5 seconds."""

    url = "/api/attendance"
    time_limit_seconds = 5

    def make_class(self, name, size, first_roll):
        academic_class = AcademicClass.objects.create(name=name, class_teacher=self.teacher)
        section = Section.objects.create(academic_class=academic_class, name="A")
        Student.objects.bulk_create(
            [
                Student(
                    name=f"{name} student {n}",
                    student_class=name,
                    roll_number=first_roll + n,
                    contact_details=f"parent{first_roll + n}@example.com",
                    section=section,
                )
                for n in range(size)
            ]
        )
        return academic_class

    def submit(self, academic_class, records):
        payload = {"classId": academic_class.pk, "date": TODAY, "records": records}
        return self.client.post(self.url, json.dumps(payload), content_type="application/json")

    def test_class_of_50_is_saved_in_one_request_under_5_seconds(self):
        academic_class = self.make_class("Grade 11", 50, first_roll=1000)
        students = list(Student.objects.filter(section__academic_class=academic_class))
        # A realistic mix: every 5th student is Absent, every 7th is Late
        records = []
        for index, student in enumerate(students, start=1):
            status = "Absent" if index % 5 == 0 else "Late" if index % 7 == 0 else "Present"
            records.append({"studentId": student.pk, "status": status})
        self.client.force_login(self.teacher)

        started = time.perf_counter()
        response = self.submit(academic_class, records)
        elapsed = time.perf_counter() - started

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["savedCount"], 50)
        self.assertEqual(Attendance.objects.filter(academic_class=academic_class).count(), 50)
        self.assertLess(elapsed, self.time_limit_seconds, f"Took {elapsed:.2f}s")

    def test_number_of_queries_does_not_grow_with_class_size(self):
        small = self.make_class("Small", 5, first_roll=100)
        large = self.make_class("Large", 50, first_roll=200)
        self.client.force_login(self.teacher)

        with CaptureQueriesContext(connection) as small_queries:
            self.assertEqual(self.submit(small, []).status_code, 201)
        with CaptureQueriesContext(connection) as large_queries:
            self.assertEqual(self.submit(large, []).status_code, 201)

        # 50 students must cost no more queries than 5 (no one-query-per-student).
        self.assertEqual(len(small_queries), len(large_queries))

class ReliabilityTests(AttendanceTestBase):
    """NFR3: no conflicting entries, and the system can be checked for uptime."""

    url = "/api/attendance"

    def test_two_submissions_at_the_same_moment_save_only_one_set(self):
        self.client.force_login(self.teacher)
        first_records = [{"studentId": self.students[0].pk, "status": "Absent"}]

        # Simulate the race: both requests pass the "already marked?" check,
        # so only the database unique constraint can stop the second one.
        with patch("attendance.services.attendance_exists", return_value=False):
            first = self.post_json(self.url, self.mark_payload(first_records))
            second = self.post_json(self.url, self.mark_payload())

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(
            Attendance.objects.filter(academic_class=self.cls, date=TODAY).count(),
            len(self.students),
        )
        # The first submission is untouched by the rejected second one
        self.assertEqual(Attendance.objects.get(student=self.students[0]).status, "Absent")

    def test_rejected_duplicate_leaves_no_partial_data(self):
        self.client.force_login(self.teacher)
        self.post_json(self.url, self.mark_payload())
        before = list(Attendance.objects.order_by("pk").values_list("pk", "status"))
        self.post_json(self.url, self.mark_payload([{"studentId": self.students[1].pk, "status": "Late"}]))
        after = list(Attendance.objects.order_by("pk").values_list("pk", "status"))
        self.assertEqual(before, after)

    def test_health_check_reports_ok_without_login(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "up"})

    def test_health_check_reports_503_when_database_is_down(self):
        with patch("attendance.views.connection.cursor", side_effect=Exception("db down")):
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "error")

class ScaleAndIndexTests(AttendanceTestBase):
    """NFR1: the Attendance table is indexed and reports stay fast with 1000+ students."""

    def index_column_sets(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(
                cursor, Attendance._meta.db_table
            )
        return [
            tuple(info["columns"])
            for info in constraints.values()
            if info["index"] or info["unique"]
        ]

    def test_attendance_table_is_indexed_on_student_class_and_date(self):
        indexed = self.index_column_sets()
        # One index covering student + class + date (the REQ3.4 unique rule) ...
        self.assertIn(("student_id", "academic_class_id", "date"), indexed)
        # ... and one for "who was marked in this class on this date" reports
        self.assertIn(("academic_class_id", "date"), indexed)

    def test_daily_view_stays_fast_with_1000_students_of_data(self):
        # 20 classes x 50 students = 1000 students, each with 3 days of attendance
        admin_classes = []
        roll = 5000
        for number in range(20):
            academic_class = AcademicClass.objects.create(
                name=f"Scale {number}", class_teacher=self.teacher
            )
            section = Section.objects.create(academic_class=academic_class, name="A")
            Student.objects.bulk_create(
                [
                    Student(
                        name=f"Scale student {number}-{n}",
                        student_class=academic_class.name,
                        roll_number=roll + n,
                        contact_details=f"scale{number}-{n}@example.com",
                        section=section,
                    )
                    for n in range(50)
                ]
            )
            roll += 100
            admin_classes.append(academic_class)

        rows = [
            Attendance(student=student, academic_class=academic_class, date=day, status="Present")
            for academic_class in admin_classes
            for student in Student.objects.filter(section__academic_class=academic_class)
            for day in ("2026-10-20", "2026-10-21", "2026-10-22")
        ]
        Attendance.objects.bulk_create(rows)
        self.assertEqual(Student.objects.count(), 1000 + len(self.students))
        self.assertEqual(Attendance.objects.count(), 3000)

        self.client.force_login(self.teacher)
        started = time.perf_counter()
        response = self.client.get(
            "/api/attendance/daily",
            {"classId": admin_classes[7].pk, "date": "2026-10-21"},
        )
        elapsed = time.perf_counter() - started

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["records"]), 50)
        self.assertLess(elapsed, 2, f"Daily view took {elapsed:.2f}s")