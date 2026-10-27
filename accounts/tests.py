import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .permissions import IsAdmin, IsStudentParent, IsTeacher

User = get_user_model()


class UserModelTests(TestCase):
    def test_default_role_is_student_parent(self):
        user = User.objects.create_user(username="kid", password="pass12345")
        self.assertEqual(user.role, User.Role.STUDENT_PARENT)

    def test_can_create_teacher(self):
        user = User.objects.create_user(username="t1", password="pass12345", role=User.Role.TEACHER)
        self.assertEqual(user.role, "TEACHER")

    def test_password_is_hashed(self):
        user = User.objects.create_user(username="a1", password="pass12345")
        self.assertNotEqual(user.password, "pass12345")
        self.assertTrue(user.check_password("pass12345"))


class LoginAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="teacher1", password="pass12345", role=User.Role.TEACHER
        )

    def post_login(self, username, password):
        return self.client.post(
            reverse("api_login"),
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )

    def test_successful_login_returns_role_and_session_token(self):
        response = self.post_login("teacher1", "pass12345")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["role"], User.Role.TEACHER)
        self.assertTrue(response.json()["session_token"])
        self.assertEqual(
            response.json()["session_token"], self.client.session.session_key
        )
        self.assertEqual(str(self.client.session["_auth_user_id"]), str(self.user.pk))

    def test_wrong_password_returns_401(self):
        response = self.post_login("teacher1", "wrong-password")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["status"], "error")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_username_returns_401(self):
        response = self.post_login("unknown-user", "pass12345")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["status"], "error")
        self.assertNotIn("_auth_user_id", self.client.session)


class RolePermissionTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")

    def set_user_role(self, role):
        self.request.user = User(username="test-user", role=role)

    def test_is_admin_allows_admin_only(self):
        permission = IsAdmin()

        self.set_user_role(User.Role.ADMIN)
        self.assertTrue(permission.has_permission(self.request, None))

        for role in (User.Role.TEACHER, User.Role.STUDENT_PARENT):
            self.set_user_role(role)
            self.assertFalse(permission.has_permission(self.request, None))

    def test_is_teacher_allows_teacher_only(self):
        permission = IsTeacher()

        self.set_user_role(User.Role.TEACHER)
        self.assertTrue(permission.has_permission(self.request, None))

        for role in (User.Role.ADMIN, User.Role.STUDENT_PARENT):
            self.set_user_role(role)
            self.assertFalse(permission.has_permission(self.request, None))

    def test_is_student_parent_allows_student_parent_only(self):
        permission = IsStudentParent()

        self.set_user_role(User.Role.STUDENT_PARENT)
        self.assertTrue(permission.has_permission(self.request, None))

        for role in (User.Role.ADMIN, User.Role.TEACHER):
            self.set_user_role(role)
            self.assertFalse(permission.has_permission(self.request, None))

    def test_role_permissions_reject_anonymous_users(self):
        self.request.user = AnonymousUser()

        for permission in (IsAdmin(), IsTeacher(), IsStudentParent()):
            self.assertFalse(permission.has_permission(self.request, None))