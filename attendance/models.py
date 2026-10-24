from django.conf import settings
from django.db import models

class Attendance(models.Model):
    """One student's attendance for one class on one date."""

    class Status(models.TextChoices):
        PRESENT = "Present", "Present"
        ABSENT = "Absent", "Absent"
        LATE = "Late", "Late"
        EXCUSED = "Excused", "Excused"

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    academic_class = models.ForeignKey(
        "students.AcademicClass",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    remarks = models.CharField(max_length=255, blank=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="attendance_marked",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "student__roll_number"]
        constraints = [
            # REQ3.4: only one record per student, class, and date
            models.UniqueConstraint(
                fields=["student", "academic_class", "date"],
                name="unique_attendance_per_student_class_date",
            ),
        ]

    def __str__(self):
        return f"{self.student} - {self.date} - {self.status}"
