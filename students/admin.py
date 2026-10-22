from django.contrib import admin

from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "student_class", "roll_number", "contact_details")
    search_fields = ("name", "student_class", "roll_number")
    list_filter = ("student_class",)
