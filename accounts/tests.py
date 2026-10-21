from django.contrib.auth import get_user_model
from django.test import TestCase

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