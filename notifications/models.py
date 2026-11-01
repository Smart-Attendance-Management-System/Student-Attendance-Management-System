from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Records who edited an attendance entry, when, and what changed."""

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    edited_at = models.DateTimeField(auto_now_add=True)
    attendance_id = models.PositiveIntegerField(null=True, blank=True)
    class_id = models.PositiveIntegerField(null=True, blank=True)
    attendance_date = models.DateField(null=True, blank=True)
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ["-edited_at"]

    def __str__(self):
        return f"AuditLog #{self.pk}: {self.old_status} -> {self.new_status}"


class Notification(models.Model):
    """REQ5.1: one email to a parent about an unexcused absence."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped (no parent email)"

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    attendance = models.ForeignKey(
        "attendance.Attendance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    recipient_email = models.EmailField(blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    last_error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"], name="notification_status_idx"),
        ]

    def __str__(self):
        return f"Notification #{self.pk} for student {self.student_id}: {self.status}"
