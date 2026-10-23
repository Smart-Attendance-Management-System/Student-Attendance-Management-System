from django.contrib import admin

from .models import Attendance

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "academic_class", "date", "status", "marked_by", "updated_at")
    list_filter = ("academic_class", "date", "status")
    readonly_fields = ("created_at", "updated_at")