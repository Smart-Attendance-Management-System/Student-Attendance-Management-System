from django.contrib import admin

from .models import AuditLog, Notification, NotificationAttempt

admin.site.register(AuditLog)


class NotificationAttemptInline(admin.TabularInline):
    model = NotificationAttempt
    extra = 0
    readonly_fields = ("attempt_number", "succeeded", "error", "attempted_at")
    can_delete = False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "recipient_email", "status", "attempts", "created_at", "sent_at")
    list_filter = ("status",)
    search_fields = ("student__name", "recipient_email")
    inlines = [NotificationAttemptInline]
