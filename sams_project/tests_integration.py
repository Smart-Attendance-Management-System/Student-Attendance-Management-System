import json

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from attendance.models import Attendance
from notifications.models import AuditLog
from students.models import AcademicClass, Section, Student

PASSWORD = "pass12345"
DATE = "2026-10-26"


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


class CrossModuleFlowTests(TestCase):
    """Admin sets up a class, a teacher marks and edits attendance, and the
    edit is written to the audit log."""

    def setUp(self):
        self.admin = User.objects.create_user(
            "admin1", password=PASSWORD, role=User.Role.ADMIN
        )
        self.teacher = User.objects.create_user(
            "teacher1", password=PASSWORD, role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            "teacher2", password=PASSWORD, role=User.Role.TEACHER
        )
        self.admin_client = Client()
        self.teacher_client = Client()
        self.other_client = Client()

    def login(self, client, username):
        response = client.post(
            reverse("login"),
            {"username": username, "password": PASSWORD, "next": "/"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", client.session)

    def build_classroom(self):
        """Admin logs in, then creates a class, a section and three students."""
        self.login(self.admin_client, "admin1")

        response = self.admin_client.post(
            reverse("classes:create"),
            {"name": "Class 10", "class_teacher": self.teacher.pk},
        )
        self.assertRedirects(
            response, reverse("classes:list"), fetch_redirect_response=False
        )
        academic_class = AcademicClass.objects.get(name="Class 10")
        self.assertEqual(academic_class.class_teacher, self.teacher)

        response = self.admin_client.post(
            reverse("sections:create"),
            {"academic_class": academic_class.pk, "name": "A"},
        )
        self.assertRedirects(
            response, reverse("sections:list"), fetch_redirect_response=False
        )
        section = Section.objects.get(academic_class=academic_class, name="A")

        names = ["Asha Rao", "Bala Iyer", "Chitra Nair"]
        for roll, name in enumerate(names, start=1):
            response = self.admin_client.post(
                reverse("students:create"),
                {
                    "name": name,
                    "student_class": "Class 10",
                    "section": section.pk,
                    "roll_number": roll,
                    "contact_details": f"parent{roll}@example.com",
                },
            )
            self.assertRedirects(
                response, reverse("students:list"), fetch_redirect_response=False
            )
        self.assertEqual(Student.objects.filter(section=section).count(), 3)
        return academic_class

    def mark(self, client, academic_class, absent_student=None):
        records = []
        if absent_student is not None:
            records.append({"studentId": absent_student.pk, "status": "Absent"})
        return post_json(
            client,
            reverse("attendance:mark"),
            {"classId": academic_class.pk, "date": DATE, "records": records},
        )

    def test_full_flow_admin_setup_teacher_marks_edits_and_audit_log(self):
        academic_class = self.build_classroom()
        students = list(
            Student.objects.filter(section__academic_class=academic_class).order_by(
                "roll_number"
            )
        )

        # Admin can see the new students on the student list page
        page = self.admin_client.get(reverse("pages:student_list"))
        self.assertContains(page, "Asha Rao")

        # Teacher logs in and opens the mark attendance page for the class
        self.login(self.teacher_client, "teacher1")
        page = self.teacher_client.get(
            reverse("pages:mark_attendance"), {"class": academic_class.pk}
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Bala Iyer")

        # Teacher marks attendance: one Absent, the others default to Present
        absent = students[1]
        response = self.mark(self.teacher_client, academic_class, absent)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["savedCount"], 3)

        saved = {
            a.student_id: a.status
            for a in Attendance.objects.filter(
                academic_class=academic_class, date=DATE
            )
        }
        self.assertEqual(saved[students[0].pk], "Present")
        self.assertEqual(saved[absent.pk], "Absent")
        self.assertEqual(saved[students[2].pk], "Present")
        self.assertEqual(AuditLog.objects.count(), 0)

        # Teacher edits the absent student's entry to Excused
        record = Attendance.objects.get(
            student=absent, academic_class=academic_class, date=DATE
        )
        self.assertEqual(record.marked_by, self.teacher)
        before = record.updated_at
        response = post_json(
            self.teacher_client,
            reverse("attendance:edit", args=[record.pk]),
            {"status": "Excused", "remarks": "Doctor's note"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["newStatus"], "Excused")

        record.refresh_from_db()
        self.assertEqual(record.status, "Excused")
        self.assertGreaterEqual(record.updated_at, before)

        # The edit created exactly one audit log entry
        self.assertEqual(AuditLog.objects.count(), 1)
        entry = AuditLog.objects.get()
        self.assertEqual(entry.edited_by, self.teacher)
        self.assertEqual(entry.attendance_id, record.pk)
        self.assertEqual(entry.class_id, academic_class.pk)
        self.assertEqual(entry.old_status, "Absent")
        self.assertEqual(entry.new_status, "Excused")

    def test_second_submission_for_same_class_and_date_is_blocked(self):
        academic_class = self.build_classroom()
        self.login(self.teacher_client, "teacher1")

        first = self.mark(self.teacher_client, academic_class)
        self.assertEqual(first.status_code, 201)
        second = self.mark(self.teacher_client, academic_class)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Attendance.objects.count(), 3)

    def test_unassigned_teacher_cannot_mark_or_edit(self):
        academic_class = self.build_classroom()
        self.login(self.teacher_client, "teacher1")
        self.login(self.other_client, "teacher2")

        # Another teacher cannot mark this class
        response = self.mark(self.other_client, academic_class)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Attendance.objects.count(), 0)

        # The assigned teacher marks it, but the other teacher cannot edit it
        self.mark(self.teacher_client, academic_class)
        record = Attendance.objects.first()
        response = post_json(
            self.other_client,
            reverse("attendance:edit", args=[record.pk]),
            {"status": "Absent"},
        )
        self.assertEqual(response.status_code, 403)
        record.refresh_from_db()
        self.assertEqual(record.status, "Present")
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_admin_cannot_mark_attendance(self):
        academic_class = self.build_classroom()
        response = self.mark(self.admin_client, academic_class)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Attendance.objects.count(), 0)
