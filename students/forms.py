from django import forms

from .models import AcademicClass, Section, Student, Subject


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ("name", "student_class", "section", "roll_number", "contact_details")
        labels = {"student_class": "Class"}
        widgets = {
            "student_class": forms.TextInput(attrs={"required": True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student_class"].required = False

    def clean(self):
        cleaned_data = super().clean()
        section = cleaned_data.get("section")
        student_class = (cleaned_data.get("student_class") or "").strip()
        if section:
            cleaned_data["student_class"] = str(section.academic_class)
        elif not student_class:
            self.add_error("student_class", "Class or section is required.")
        return cleaned_data


class AcademicClassForm(forms.ModelForm):
    class Meta:
        model = AcademicClass
        fields = ("name",)


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ("academic_class", "name")


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ("name", "code")
