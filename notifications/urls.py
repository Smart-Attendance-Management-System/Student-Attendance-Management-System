from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("audit-log/", views.audit_log_page, name="audit_log"),
    path("api/audit-log", views.audit_log_api, name="audit_log_api"),
]
