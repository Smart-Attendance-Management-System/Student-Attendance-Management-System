from django.contrib import admin

from .models import AcademicClass, Section, Student, Subject


@admin.register(AcademicClass)
class AcademicClassAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "academic_class")
    list_filter = ("academic_class",)
    search_fields = ("name", "academic_class__name")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "student_class", "section", "roll_number", "parent", "contact_details")
    search_fields = ("name", "student_class", "roll_number")
    list_filter = ("student_class",)
