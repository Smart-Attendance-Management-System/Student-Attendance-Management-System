import csv
from io import BytesIO, StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

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


class BulkStudentImportTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="import-admin",
            password="adminpass123",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="import-teacher",
            password="teacherpass123",
            role=User.Role.TEACHER,
        )
        self.academic_class = AcademicClass.objects.create(name="Grade 10")
        self.section = Section.objects.create(
            academic_class=self.academic_class,
            name="A",
        )

    def csv_file(self, rows, name="students.csv"):
        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["name", "class", "section", "roll_number", "contact_details"],
        )
        writer.writeheader()
        writer.writerows(rows)
        return SimpleUploadedFile(
            name,
            output.getvalue().encode("utf-8"),
            content_type="text/csv",
        )

    def excel_file(self, rows, name="students.xlsx"):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(["name", "class", "section", "roll_number", "contact_details"])
        for row in rows:
            worksheet.append(
                [
                    row["name"],
                    row["class"],
                    row.get("section", ""),
                    row["roll_number"],
                    row["contact_details"],
                ]
            )
        content = BytesIO()
        workbook.save(content)
        return SimpleUploadedFile(
            name,
            content.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_admin_can_import_valid_csv(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:import"),
            {
                "file": self.csv_file(
                    [
                        {
                            "name": "CSV Student",
                            "class": "Grade 10",
                            "section": "A",
                            "roll_number": "101",
                            "contact_details": "csv@example.com",
                        }
                    ]
                )
            },
        )

        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(roll_number=101)
        self.assertEqual(student.section, self.section)
        self.assertEqual(student.student_class, "Grade 10")

    def test_admin_can_import_supported_excel_file(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:import"),
            {
                "file": self.excel_file(
                    [
                        {
                            "name": "Excel Student",
                            "class": "Grade 10",
                            "section": "A",
                            "roll_number": 102,
                            "contact_details": "excel@example.com",
                        }
                    ]
                )
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Student.objects.filter(roll_number=102).exists())

    def test_empty_file_is_rejected_without_writes(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:import"),
            {"file": SimpleUploadedFile("empty.csv", b"", content_type="text/csv")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Student.objects.count(), 0)

    def test_unsupported_file_type_is_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:import"),
            {
                "file": SimpleUploadedFile(
                    "students.txt",
                    b"name,class,roll_number,contact_details\nA,Grade 10,103,a@example.com",
                    content_type="text/plain",
                )
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "CSV file or an .xlsx Excel file", status_code=400)

    def test_missing_headers_and_invalid_values_are_rejected(self):
        self.client.force_login(self.admin)
        missing_headers = SimpleUploadedFile(
            "missing.csv",
            b"name,class\nStudent,Grade 10",
            content_type="text/csv",
        )
        response = self.client.post(
            reverse("students:import"),
            {"file": missing_headers},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Required columns are missing", status_code=400)
        self.assertEqual(Student.objects.count(), 0)

        response = self.client.post(
            reverse("students:import"),
            {
                "file": self.csv_file(
                    [
                        {
                            "name": "Invalid Student",
                            "class": "Grade 10",
                            "section": "A",
                            "roll_number": "not-a-number",
                            "contact_details": "invalid@example.com",
                        }
                    ],
                    name="invalid.csv",
                )
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Student.objects.count(), 0)

    def test_duplicate_roll_numbers_are_rejected_atomically(self):
        existing = Student.objects.create(
            name="Existing Student",
            student_class="Grade 10",
            roll_number=104,
            contact_details="existing@example.com",
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:import"),
            {
                "file": self.csv_file(
                    [
                        {
                            "name": "New Student",
                            "class": "Grade 10",
                            "section": "A",
                            "roll_number": "105",
                            "contact_details": "new@example.com",
                        },
                        {
                            "name": "Duplicate Student",
                            "class": "Grade 10",
                            "section": "A",
                            "roll_number": "105",
                            "contact_details": "duplicate@example.com",
                        },
                    ],
                    name="duplicates.csv",
                )
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Student.objects.count(), 1)
        self.assertTrue(Student.objects.filter(pk=existing.pk).exists())

    def test_unknown_class_or_section_is_rejected_without_writes(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:import"),
            {
                "file": self.csv_file(
                    [
                        {
                            "name": "Unknown Class Student",
                            "class": "Grade 11",
                            "section": "A",
                            "roll_number": "106",
                            "contact_details": "unknown@example.com",
                        }
                    ],
                    name="unknown.csv",
                )
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "was not found", status_code=400)
        self.assertEqual(Student.objects.count(), 0)

    def test_non_admin_and_unauthenticated_users_cannot_import(self):
        upload = self.csv_file(
            [
                {
                    "name": "Denied Student",
                    "class": "Grade 10",
                    "section": "A",
                    "roll_number": "107",
                    "contact_details": "denied@example.com",
                }
            ],
            name="denied.csv",
        )
        self.client.force_login(self.teacher)
        self.assertEqual(
            self.client.post(reverse("students:import"), {"file": upload}).status_code,
            403,
        )

        self.client.logout()
        response = self.client.get(reverse("students:import"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])
