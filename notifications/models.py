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
