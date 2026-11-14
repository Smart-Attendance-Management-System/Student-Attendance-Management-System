from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AcademicClass(models.Model):
    name = models.CharField(max_length=50, unique=True)
    class_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_classes",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "class"
        verbose_name_plural = "classes"

    def clean(self):
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Class name is required."})
        if self.class_teacher and self.class_teacher.role != type(self.class_teacher).Role.TEACHER:
            raise ValidationError(
                {"class_teacher": "The class teacher must have the Teacher role."}
            )

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
    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="children",
        blank=True,
        null=True,
        limit_choices_to={"role": "STUDENT_PARENT"},
        help_text="The Student/Parent account that can view this student's attendance.",
    )

    class Meta:
        ordering = ["section__academic_class__name", "section__name", "roll_number"]
        verbose_name = "student profile"
        verbose_name_plural = "student profiles"

    MISSING_SECTION_MESSAGE = (
        "Section is required. A student without a section does not appear on the Mark attendance page."
    )

    def clean(self):
        super().clean()
        if not self.section_id:
            raise ValidationError({"section": self.MISSING_SECTION_MESSAGE})
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Student name is required."})
        if self.roll_number is None or self.roll_number <= 0:
            raise ValidationError({"roll_number": "Roll number must be a positive number."})
        if not self.contact_details or not self.contact_details.strip():
            raise ValidationError({"contact_details": "Contact details are required."})

    @property
    def class_name(self):
        """The student's class, always taken from their section."""
        if self.section_id is None:
            return ""
        return self.section.academic_class.name

    def __str__(self):
        if self.section_id is None:
            return self.name
        return f"{self.name} ({self.section})"
