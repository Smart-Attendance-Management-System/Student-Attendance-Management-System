import json

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from .forms import UserAccountForm
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
        self.assertTrue(user.password.startswith("bcrypt_sha256$$2b$"))
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

    def test_successful_login_upgrades_legacy_password_hash_to_bcrypt(self):
        self.user.password = make_password("pass12345", hasher="pbkdf2_sha256")
        self.user.save(update_fields=["password"])

        response = self.post_login("teacher1", "pass12345")

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.password.startswith("bcrypt_sha256$$2b$"))

    def test_wrong_password_returns_401(self):
        response = self.post_login("teacher1", "wrong-password")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["message"], "Invalid username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_username_returns_401(self):
        response = self.post_login("unknown-user", "pass12345")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["message"], "Invalid username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_password_and_unknown_username_return_identical_messages(self):
        wrong_password = self.post_login("teacher1", "wrong-password")
        unknown_username = self.post_login("unknown-user", "pass12345")

        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_username.status_code, 401)
        self.assertEqual(
            wrong_password.json()["message"],
            unknown_username.json()["message"],
        )


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


class UserAccountManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="account-admin",
            password="pass12345",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="account-teacher",
            password="pass12345",
            role=User.Role.TEACHER,
        )
        self.client.force_login(self.admin)

    def test_admin_can_create_edit_and_delete_user(self):
        list_response = self.client.get(reverse("accounts:list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "User Accounts")

        create_response = self.client.post(
            reverse("accounts:create"),
            {
                "username": "new-teacher",
                "email": "new-teacher@example.com",
                "role": User.Role.TEACHER,
                "password": "N3w!Account-Password-2026",
            },
        )
        self.assertRedirects(create_response, reverse("accounts:list"))
        account = User.objects.get(username="new-teacher")
        self.assertEqual(account.email, "new-teacher@example.com")
        self.assertEqual(account.role, User.Role.TEACHER)
        self.assertTrue(account.check_password("N3w!Account-Password-2026"))

        edit_response = self.client.post(
            reverse("accounts:update", args=[account.pk]),
            {
                "username": "new-teacher",
                "email": "updated@example.com",
                "role": User.Role.STUDENT_PARENT,
                "password": "",
            },
        )
        self.assertRedirects(edit_response, reverse("accounts:list"))
        account.refresh_from_db()
        self.assertEqual(account.email, "updated@example.com")
        self.assertEqual(account.role, User.Role.STUDENT_PARENT)
        self.assertTrue(account.check_password("N3w!Account-Password-2026"))

        delete_response = self.client.post(
            reverse("accounts:delete", args=[account.pk])
        )
        self.assertRedirects(delete_response, reverse("accounts:list"))
        self.assertFalse(User.objects.filter(pk=account.pk).exists())

    def test_duplicate_username_is_rejected(self):
        response = self.client.post(
            reverse("accounts:create"),
            {
                "username": self.teacher.username,
                "email": "duplicate@example.com",
                "role": User.Role.TEACHER,
                "password": "N3w!Account-Password-2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.filter(username=self.teacher.username).count(), 1)

    def test_role_change_updates_permissions_for_existing_session(self):
        teacher_client = Client()
        teacher_client.force_login(self.teacher)

        self.assertEqual(
            teacher_client.get(reverse("accounts:list")).status_code, 403
        )
        self.assertEqual(
            teacher_client.get(reverse("pages:mark_attendance")).status_code, 200
        )

        response = self.client.post(
            reverse("accounts:update", args=[self.teacher.pk]),
            {
                "username": self.teacher.username,
                "email": self.teacher.email,
                "role": User.Role.ADMIN,
                "password": "",
            },
        )
        self.assertRedirects(response, reverse("accounts:list"))

        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.role, User.Role.ADMIN)
        self.assertEqual(
            teacher_client.get(reverse("accounts:list")).status_code, 200
        )
        self.assertEqual(
            teacher_client.get(reverse("pages:mark_attendance")).status_code, 302
        )

    def test_non_admin_cannot_manage_user_accounts(self):
        self.client.force_login(self.teacher)
        requests = (
            ("get", reverse("accounts:list")),
            ("get", reverse("accounts:create")),
            ("post", reverse("accounts:update", args=[self.admin.pk])),
            ("post", reverse("accounts:delete", args=[self.admin.pk])),
        )

        for method, path in requests:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path)
                self.assertEqual(response.status_code, 403)

    def test_account_form_requires_password_when_creating_user(self):
        form = UserAccountForm(
            data={
                "username": "no-password",
                "email": "",
                "role": User.Role.TEACHER,
                "password": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)