from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import AcademicClass, Section, Student, Subject

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


class ClassSectionSubjectTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="catalog-admin",
            password="adminpass123",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="catalog-teacher",
            password="teacherpass123",
            role=User.Role.TEACHER,
        )

    def test_admin_can_create_view_update_and_delete_records(self):
        self.client.force_login(self.admin)

        class_response = self.client.post(
            reverse("classes:create"),
            {"name": "Grade 10"},
        )
        self.assertEqual(class_response.status_code, 302)
        academic_class = AcademicClass.objects.get(name="Grade 10")
        self.assertEqual(
            self.client.get(reverse("classes:detail", args=[academic_class.pk])).status_code,
            200,
        )

        section_response = self.client.post(
            reverse("sections:create"),
            {"academic_class": academic_class.pk, "name": "A"},
        )
        self.assertEqual(section_response.status_code, 302)
        section = Section.objects.get(academic_class=academic_class, name="A")

        update_response = self.client.post(
            reverse("sections:update", args=[section.pk]),
            {"academic_class": academic_class.pk, "name": "B"},
        )
        self.assertEqual(update_response.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.name, "B")

        subject_response = self.client.post(
            reverse("subjects:create"),
            {"name": "Mathematics", "code": "MATH"},
        )
        self.assertEqual(subject_response.status_code, 302)
        subject = Subject.objects.get(code="MATH")
        self.assertEqual(self.client.get(reverse("subjects:list")).status_code, 200)

        self.assertEqual(
            self.client.post(reverse("subjects:delete", args=[subject.pk])).status_code,
            302,
        )
        self.assertFalse(Subject.objects.filter(pk=subject.pk).exists())
        self.assertEqual(
            self.client.post(reverse("sections:delete", args=[section.pk])).status_code,
            302,
        )
        self.assertFalse(Section.objects.filter(pk=section.pk).exists())
        self.assertEqual(
            self.client.post(reverse("classes:delete", args=[academic_class.pk])).status_code,
            302,
        )
        self.assertFalse(AcademicClass.objects.filter(pk=academic_class.pk).exists())

    def test_duplicate_class_section_combination_is_rejected(self):
        academic_class = AcademicClass.objects.create(name="Grade 11")
        Section.objects.create(academic_class=academic_class, name="A")
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("sections:create"),
            {"academic_class": academic_class.pk, "name": "A"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(Section.objects.filter(academic_class=academic_class).count(), 1)

    def test_non_admin_cannot_manage_classes_sections_or_subjects(self):
        self.client.force_login(self.teacher)
        endpoints = (
            ("classes:create", {"name": "Grade 12"}),
            ("sections:create", {"academic_class": "", "name": "A"}),
            ("subjects:create", {"name": "Physics", "code": "PHY"}),
        )

        for endpoint, data in endpoints:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.post(reverse(endpoint), data).status_code, 403)

    def test_unauthenticated_catalog_access_redirects_to_login(self):
        for endpoint in ("classes:list", "sections:list", "subjects:list"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(reverse(endpoint))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login", response["Location"])

    def test_invalid_catalog_data_is_rejected(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse("classes:create"), {"name": ""})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "required")

    def test_student_can_reference_section_and_section_deletion_is_protected(self):
        academic_class = AcademicClass.objects.create(name="Grade 9")
        section = Section.objects.create(academic_class=academic_class, name="A")
        student = Student.objects.create(
            name="Section Student",
            student_class=str(academic_class),
            section=section,
            roll_number=901,
            contact_details="student@example.com",
        )

        self.assertEqual(student.section, section)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("sections:delete", args=[section.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Section.objects.filter(pk=section.pk).exists())
        self.assertTrue(Student.objects.filter(pk=student.pk).exists())
