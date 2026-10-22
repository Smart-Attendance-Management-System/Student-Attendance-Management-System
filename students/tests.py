from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Student

User = get_user_model()


class StudentProfileTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin1",
            password="adminpass123",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="teacher1",
            password="teacherpass123",
            role=User.Role.TEACHER,
        )
        self.student = Student.objects.create(
            name="Alice Johnson",
            student_class="Grade 10",
            roll_number=12,
            contact_details="alice@example.com / 555-0101",
        )

    def test_admin_creates_student_successfully(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:create"),
            {
                "name": "Bob Smith",
                "student_class": "Grade 9",
                "roll_number": 33,
                "contact_details": "bob@example.com",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Student.objects.filter(roll_number=33).exists())

    def test_student_profiles_can_be_listed_and_viewed(self):
        self.client.force_login(self.admin)
        list_response = self.client.get(reverse("students:list"))
        self.assertEqual(list_response.status_code, 200)
        detail_response = self.client.get(reverse("students:detail", args=[self.student.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Alice Johnson")

    def test_admin_can_update_student(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:update", args=[self.student.pk]),
            {
                "name": "Alice Updated",
                "student_class": "Grade 11",
                "roll_number": 12,
                "contact_details": "alice.updated@example.com",
            },
        )
        self.student.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.student.name, "Alice Updated")

    def test_admin_can_delete_student(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("students:delete", args=[self.student.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())

    def test_duplicate_roll_numbers_are_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:create"),
            {
                "name": "Charlie Brown",
                "student_class": "Grade 10",
                "roll_number": 12,
                "contact_details": "charlie@example.com",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_non_admin_cannot_create_edit_or_delete_student_profiles(self):
        self.client.force_login(self.teacher)
        create_response = self.client.post(
            reverse("students:create"),
            {
                "name": "Denied User",
                "student_class": "Grade 10",
                "roll_number": 99,
                "contact_details": "denied@example.com",
            },
        )
        self.assertEqual(create_response.status_code, 403)

        update_response = self.client.post(
            reverse("students:update", args=[self.student.pk]),
            {
                "name": "Denied Edit",
                "student_class": "Grade 10",
                "roll_number": 12,
                "contact_details": "denied@example.com",
            },
        )
        self.assertEqual(update_response.status_code, 403)

        delete_response = self.client.post(reverse("students:delete", args=[self.student.pk]))
        self.assertEqual(delete_response.status_code, 403)

    def test_unauthenticated_access_is_handled_according_to_rules(self):
        response = self.client.get(reverse("students:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_invalid_or_missing_required_data_is_rejected(self):
        self.client.force_login(self.admin)
        invalid_response = self.client.post(
            reverse("students:create"),
            {
                "name": "",
                "student_class": "",
                "roll_number": "",
                "contact_details": "",
            },
        )
        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, "required")

    def test_model_validates_required_fields(self):
        student = Student(
            name="",
            student_class="",
            roll_number=0,
            contact_details="",
        )
        with self.assertRaises(ValidationError):
            student.full_clean()
