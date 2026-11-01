from django.contrib import admin

from .models import AuditLog, Notification

admin.site.register(AuditLog)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "recipient_email", "status", "created_at", "sent_at")
    list_filter = ("status",)
    search_fields = ("student__name", "recipient_email")
