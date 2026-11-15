from django import forms
from django.contrib.auth import get_user_model

from .models import AcademicClass, Section, Student, Subject

User = get_user_model()


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ("name", "section", "roll_number", "contact_details")
        labels = {"section": "Class and section"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["section"].required = True
        self.fields["section"].error_messages["required"] = Student.MISSING_SECTION_MESSAGE
        self.fields["section"].queryset = Section.objects.select_related("academic_class")


class AcademicClassForm(forms.ModelForm):
    class Meta:
        model = AcademicClass
        fields = ("name", "class_teacher")
        labels = {"class_teacher": "Class Teacher"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["class_teacher"].queryset = User.objects.filter(
            role=User.Role.TEACHER
        )


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ("academic_class", "name")


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ("name", "code")
