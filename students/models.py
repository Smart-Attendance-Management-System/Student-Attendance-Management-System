from django.core.exceptions import ValidationError
from django.db import models


class AcademicClass(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "class"
        verbose_name_plural = "classes"

    def clean(self):
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Class name is required."})

    def __str__(self):
        return self.name


class Section(models.Model):
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.PROTECT,
        related_name="sections",
    )
    name = models.CharField(max_length=50)

    class Meta:
        ordering = ["academic_class__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_class", "name"],
                name="unique_class_section",
            ),
        ]

    def clean(self):
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Section name is required."})

    def __str__(self):
        return f"{self.academic_class} - {self.name}"


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def clean(self):
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Subject name is required."})
        if self.code and not self.code.strip():
            raise ValidationError({"code": "Subject code cannot be blank."})

    def __str__(self):
        return f"{self.code} - {self.name}" if self.code else self.name


class Student(models.Model):
    name = models.CharField(
        max_length=120,
        help_text="Full name of the student.",
    )
    student_class = models.CharField(
        max_length=50,
        help_text="Class or section assigned to the student.",
    )
    roll_number = models.PositiveIntegerField(
        unique=True,
        help_text="Unique roll number for the student.",
        error_messages={"unique": "A student with this roll number already exists."},
    )
    contact_details = models.TextField(
        help_text="Phone number, email, or emergency contact details.",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="students",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["student_class", "roll_number"]
        verbose_name = "student profile"
        verbose_name_plural = "student profiles"

    def clean(self):
        super().clean()
        if self.section:
            self.student_class = str(self.section.academic_class)
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Student name is required."})
        if not self.student_class or not self.student_class.strip():
            raise ValidationError({"student_class": "Student class is required."})
        if self.roll_number is None or self.roll_number <= 0:
            raise ValidationError({"roll_number": "Roll number must be a positive number."})
        if not self.contact_details or not self.contact_details.strip():
            raise ValidationError({"contact_details": "Contact details are required."})

    def __str__(self):
        return f"{self.name} ({self.student_class})"
