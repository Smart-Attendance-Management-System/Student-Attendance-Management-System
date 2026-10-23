from django.test import TestCase
from django.urls import reverse

from accounts.models import User


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
