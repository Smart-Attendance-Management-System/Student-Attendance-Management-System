from django.contrib import admin

from . import services
from .models import Attendance

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "academic_class", "date", "status", "marked_by", "updated_at")
    list_filter = ("academic_class", "date", "status")
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if change:
            services.edit_attendance(
                request.user,
                obj,
                form.cleaned_data["status"],
                form.cleaned_data.get("remarks"),
                allow_admin=True,
            )
            return
        super().save_model(request, obj, form, change)