from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import AuditLog
from .services import log_attendance_edit


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
