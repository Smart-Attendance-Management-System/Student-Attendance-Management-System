from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        TEACHER = "TEACHER", "Teacher"
        STUDENT_PARENT = "STUDENT_PARENT", "Student/Parent"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT_PARENT)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"