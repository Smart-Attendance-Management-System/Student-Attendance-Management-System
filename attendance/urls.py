from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    path("api/attendance", views.mark_attendance_api, name="mark"),
    path("api/attendance/<int:pk>", views.edit_attendance_api, name="edit"),
    path("api/attendance/daily", views.daily_attendance_api, name="daily"),
    path("health/", views.health_check, name="health"),
    path("api/attendance/student/<int:student_id>", views.student_history_api, name="student_history"),
]