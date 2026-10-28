from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from students.models import AcademicClass

class PageAccessTests(TestCase):
    def make_user(self, role):
        return User.objects.create_user(
            username=role.lower(), password="pass12345", role=role
        )

    def test_login_page_loads(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")

    def test_anonymous_is_sent_to_login(self):
        for name in ("pages:student_list", "pages:mark_attendance"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse("login")))

    def test_teacher_can_open_both_pages(self):
        self.client.force_login(self.make_user(User.Role.TEACHER))
        self.assertEqual(self.client.get(reverse("pages:student_list")).status_code, 200)
        response = self.client.get(reverse("pages:mark_attendance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mark attendance")

    def test_admin_can_open_student_list(self):
        self.client.force_login(self.make_user(User.Role.ADMIN))
        self.assertEqual(self.client.get(reverse("pages:student_list")).status_code, 200)

    def test_admin_is_redirected_from_mark_attendance(self):
        self.client.force_login(self.make_user(User.Role.ADMIN))
        response = self.client.get(reverse("pages:mark_attendance"))
        self.assertRedirects(response, reverse("pages:home"), fetch_redirect_response=False)

    def test_student_parent_is_redirected_from_both_pages(self):
        self.client.force_login(self.make_user(User.Role.STUDENT_PARENT))
        for name in ("pages:student_list", "pages:mark_attendance"):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, reverse("pages:home"), fetch_redirect_response=False)

    def test_header_shows_name_role_and_logout(self):
        self.client.force_login(self.make_user(User.Role.TEACHER))
        response = self.client.get(reverse("pages:mark_attendance"))
        self.assertContains(response, "Teacher")
        self.assertContains(response, "Logout")


@override_settings(SESSION_COOKIE_AGE=15 * 60, SESSION_SAVE_EVERY_REQUEST=True)
class SessionInactivityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="session-teacher",
            password="pass12345",
            role=User.Role.TEACHER,
        )
        self.login_time = timezone.now()
        with patch("django.utils.timezone.now", return_value=self.login_time):
            self.client.force_login(self.user)

    def get_protected_page_at(self, moment):
        with patch("django.utils.timezone.now", return_value=moment):
            return self.client.get(reverse("pages:mark_attendance"))

    def test_expired_session_is_rejected(self):
        response = self.get_protected_page_at(
            self.login_time + timedelta(minutes=15, seconds=1)
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_activity_just_before_timeout_resets_session_expiry(self):
        first_activity = self.login_time + timedelta(minutes=14, seconds=59)
        second_activity = first_activity + timedelta(minutes=14, seconds=59)
        after_refreshed_expiry = second_activity + timedelta(minutes=15, seconds=1)

        first_response = self.get_protected_page_at(first_activity)
        self.assertEqual(first_response.status_code, 200)

        second_response = self.get_protected_page_at(second_activity)
        self.assertEqual(second_response.status_code, 200)

        expired_response = self.get_protected_page_at(after_refreshed_expiry)
        self.assertEqual(expired_response.status_code, 302)
        self.assertTrue(expired_response.url.startswith(reverse("login")))

class DailyPageAndNavigationTests(TestCase):
    def make_user(self, role, **extra):
        return User.objects.create_user(
            username=role.lower(), password="pass12345", role=role, **extra
        )

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse("pages:daily_attendance"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_student_parent_is_redirected(self):
        self.client.force_login(self.make_user(User.Role.STUDENT_PARENT))
        response = self.client.get(reverse("pages:daily_attendance"))
        self.assertRedirects(response, reverse("pages:home"), fetch_redirect_response=False)

    def test_teacher_only_sees_their_own_classes(self):
        teacher = self.make_user(User.Role.TEACHER)
        other = User.objects.create_user(
            username="teacher2", password="pass12345", role=User.Role.TEACHER
        )
        AcademicClass.objects.create(name="Grade 10", class_teacher=teacher)
        AcademicClass.objects.create(name="Grade 9", class_teacher=other)
        self.client.force_login(teacher)
        response = self.client.get(reverse("pages:daily_attendance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Daily attendance")
        self.assertContains(response, "Grade 10")
        self.assertNotContains(response, "Grade 9")

    def test_admin_sees_every_class(self):
        teacher = User.objects.create_user(
            username="teacher1", password="pass12345", role=User.Role.TEACHER
        )
        AcademicClass.objects.create(name="Grade 10", class_teacher=teacher)
        AcademicClass.objects.create(name="Grade 9")
        self.client.force_login(self.make_user(User.Role.ADMIN))
        response = self.client.get(reverse("pages:daily_attendance"))
        self.assertContains(response, "Grade 10")
        self.assertContains(response, "Grade 9")

    def test_header_links_match_the_role(self):
        self.client.force_login(self.make_user(User.Role.TEACHER))
        response = self.client.get(reverse("pages:mark_attendance"))
        self.assertContains(response, "Daily view")
        self.assertContains(response, "Mark attendance")
        self.assertNotContains(response, "Admin site")

    def test_staff_user_sees_link_to_admin_site(self):
        self.client.force_login(self.make_user(User.Role.ADMIN, is_staff=True))
        response = self.client.get(reverse("pages:student_list"))
        self.assertContains(response, reverse("admin:index"))
        self.assertContains(response, "Admin site")

    def test_login_page_links_to_admin_site(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, reverse("admin:index"))
