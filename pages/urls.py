from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("pages/students/", views.student_list, name="student_list"),
    path("pages/attendance/", views.mark_attendance, name="mark_attendance"),
    path("pages/daily/", views.daily_attendance, name="daily_attendance"),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
]
