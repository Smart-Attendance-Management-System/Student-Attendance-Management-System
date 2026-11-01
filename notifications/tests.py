import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from attendance.models import Attendance
from students.models import AcademicClass, Section, Student

from .models import AuditLog, Notification
from .services import log_attendance_edit, notify_absence


class AuditLogTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="teacher1", password="testpass123"
        )

    def test_log_saves_who_when_and_what(self):
        entry = log_attendance_edit(self.user, 5, "Present", "Absent")
        self.assertEqual(entry.edited_by, self.user)
        self.assertEqual(entry.old_status, "Present")
        self.assertEqual(entry.new_status, "Absent")
        self.assertIsNotNone(entry.edited_at)

    def test_log_works_without_user(self):
        entry = log_attendance_edit(None, 5, "Late", "Present")
        self.assertIsNone(entry.edited_by)

    def test_editing_attendance_creates_audit_entry(self):
        before = AuditLog.objects.count()
        log_attendance_edit(self.user, 7, "Absent", "Excused", class_id=1)
        self.assertEqual(AuditLog.objects.count(), before + 1)
        self.assertEqual(AuditLog.objects.first().class_id, 1)


ABSENCE_DATE = "2026-10-27"


class AbsenceNotificationTestBase(TestCase):
    """One class taught by teacher1 with three students, each with a parent account."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher1", password="pass12345", role=User.Role.TEACHER
        )
        self.cls = AcademicClass.objects.create(name="Grade 9", class_teacher=self.teacher)
        section = Section.objects.create(academic_class=self.cls, name="A")
        self.parents = []
        self.students = []
        for n in (1, 2, 3):
            parent = User.objects.create_user(
                username=f"parent{n}",
                password="pass12345",
                email=f"parent{n}@example.com",
                role=User.Role.STUDENT_PARENT,
            )
            self.parents.append(parent)
            self.students.append(
                Student.objects.create(
                    name=f"Child {n}",
                    student_class="Grade 9",
                    roll_number=100 + n,
                    contact_details="School office",
                    section=section,
                    parent=parent,
                )
            )
        self.client.force_login(self.teacher)

    def submit(self, statuses):
        """Mark the class through the real API: statuses maps student index -> status."""
        records = [
            {"studentId": self.students[i].pk, "status": status}
            for i, status in statuses.items()
        ]
        return self.client.post(
            reverse("attendance:mark"),
            json.dumps({"classId": self.cls.pk, "date": ABSENCE_DATE, "records": records}),
            content_type="application/json",
        )


class AbsenceNotificationIntegrationTests(AbsenceNotificationTestBase):
    """TC-08 / REQ5.1: Absent creates a notification, Excused and Late do not."""

    def test_absent_sends_email_to_parent_and_saves_record(self):
        response = self.submit({0: "Absent"})
        self.assertEqual(response.status_code, 201)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["parent1@example.com"])
        self.assertIn("Child 1", mail.outbox[0].subject)
        self.assertIn("Absent", mail.outbox[0].body)

        notification = Notification.objects.get()
        self.assertEqual(notification.student, self.students[0])
        self.assertEqual(notification.recipient_email, "parent1@example.com")
        self.assertEqual(notification.status, Notification.Status.SENT)
        self.assertIsNotNone(notification.sent_at)
        self.assertEqual(notification.attendance.status, "Absent")

    def test_excused_and_late_do_not_notify(self):
        response = self.submit({0: "Excused", 1: "Late"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(Notification.objects.exists())

    def test_present_does_not_notify(self):
        self.submit({})  # everyone defaults to Present
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(Notification.objects.exists())

    def test_only_absent_students_in_a_mixed_class_are_notified(self):
        self.submit({0: "Absent", 1: "Excused", 2: "Late"})
        self.assertEqual(
            list(Notification.objects.values_list("student_id", flat=True)),
            [self.students[0].pk],
        )
        self.assertEqual([m.to for m in mail.outbox], [["parent1@example.com"]])

    def test_editing_to_absent_notifies_and_editing_to_excused_does_not(self):
        self.submit({})
        record = Attendance.objects.get(student=self.students[1])
        edit_url = reverse("attendance:edit", args=[record.pk])

        self.client.post(edit_url, json.dumps({"status": "Excused"}), content_type="application/json")
        self.assertEqual(len(mail.outbox), 0)

        self.client.post(edit_url, json.dumps({"status": "Absent"}), content_type="application/json")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["parent2@example.com"])
        self.assertEqual(Notification.objects.get().attendance, record)

    def test_student_without_parent_email_is_recorded_as_skipped(self):
        self.parents[0].email = ""
        self.parents[0].save()
        self.submit({0: "Absent"})
        self.assertEqual(len(mail.outbox), 0)
        notification = Notification.objects.get()
        self.assertEqual(notification.status, Notification.Status.SKIPPED)

    def test_email_failure_does_not_block_saving_attendance(self):
        with patch("notifications.services.send_mail", side_effect=OSError("SMTP down")):
            response = self.submit({0: "Absent"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Attendance.objects.filter(date=ABSENCE_DATE).count(), 3)
        self.assertEqual(Notification.objects.get().status, Notification.Status.FAILED)


class NotifyAbsenceUnitTests(AbsenceNotificationTestBase):
    def test_notify_absence_ignores_non_absent_statuses(self):
        for status in ("Present", "Late", "Excused"):
            record = Attendance(
                student=self.students[0], academic_class=self.cls,
                date=ABSENCE_DATE, status=status,
            )
            self.assertIsNone(notify_absence(record))
        self.assertFalse(Notification.objects.exists())
