from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    path("api/attendance", views.mark_attendance_api, name="mark"),
    path("api/attendance/<int:pk>", views.edit_attendance_api, name="edit"),
]