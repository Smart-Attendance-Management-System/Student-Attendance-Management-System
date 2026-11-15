import csv
from io import BytesIO, StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook, load_workbook

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
        self.student_parent = User.objects.create_user(
            username="catalog-student",
            password="test-password-123",
            role=User.Role.STUDENT_PARENT,
        )
        self.grade_9 = AcademicClass.objects.create(name="Grade 9")
        self.grade_9_a = Section.objects.create(academic_class=self.grade_9, name="A")
        self.grade_11 = AcademicClass.objects.create(name="Grade 11")
        self.grade_11_a = Section.objects.create(academic_class=self.grade_11, name="A")
        self.student = Student.objects.create(
            name="Alice Johnson",
            roll_number=12,
            contact_details="alice@example.com / 555-0101",
        )

    def test_admin_creates_student_successfully(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:create"),
            {
                "name": "Bob Smith",
                "section": self.grade_9_a.pk,
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
                "section": self.grade_11_a.pk,
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
                "roll_number": 99,
                "contact_details": "denied@example.com",
            },
        )
        self.assertEqual(create_response.status_code, 403)

        update_response = self.client.post(
            reverse("students:update", args=[self.student.pk]),
            {
                "name": "Denied Edit",
                "roll_number": 12,
                "contact_details": "denied@example.com",
            },
        )
        self.assertEqual(update_response.status_code, 403)

        delete_response = self.client.post(reverse("students:delete", args=[self.student.pk]))
        self.assertEqual(delete_response.status_code, 403)

    def test_teacher_receives_403_from_admin_only_endpoint(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("students:create"),
            {
                "name": "Denied User",
                "roll_number": 99,
                "contact_details": "denied@example.com",
            },
        )

        self.assertEqual(response.status_code, 403)

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
                "roll_number": "",
                "contact_details": "",
            },
        )
        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, "required")

    def test_model_validates_required_fields(self):
        student = Student(
            name="",
            roll_number=0,
            contact_details="",
        )
        with self.assertRaises(ValidationError):
            student.full_clean()


class SharedLayoutIntegrationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="layout-admin",
            password="pass12345",
            first_name="Ada",
            last_name="Admin",
            role=User.Role.ADMIN,
        )
        self.student = Student.objects.create(
            name="Layout Student",
            roll_number=101,
            contact_details="layout@example.com",
        )
        self.academic_class = AcademicClass.objects.create(name="Grade 10")
        self.client.force_login(self.admin)

    def test_all_student_and_catalog_templates_use_shared_authenticated_layout(self):
        pages = (
            ("students:list", (), "students/student_list.html"),
            ("students:detail", (self.student.pk,), "students/student_detail.html"),
            ("students:create", (), "students/student_form.html"),
            ("students:import", (), "students/student_import.html"),
            ("classes:list", (), "students/catalog_list.html"),
            ("classes:detail", (self.academic_class.pk,), "students/catalog_detail.html"),
            ("classes:create", (), "students/catalog_form.html"),
        )

        for url_name, args, template_name in pages:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name, args=args))

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template_name)
                self.assertTemplateUsed(response, "pages/base.html")
                self.assertContains(response, 'href="/accounts/users/"')
                self.assertContains(response, "Ada Admin")
                self.assertContains(response, "Admin")
                self.assertContains(response, 'action="/accounts/logout/"')
                self.assertContains(response, "name=\"csrfmiddlewaretoken\"")


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

        self.student_parent = User.objects.create_user(
            username="catalog-student",
            password="test-password-123",
            role=User.Role.STUDENT_PARENT,
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

    def test_class_can_be_created_without_a_teacher(self):
        academic_class = AcademicClass.objects.create(name="Unassigned Class")

        self.assertIsNone(academic_class.class_teacher)

    def test_class_form_only_lists_teachers_and_persists_assignment(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("classes:create"))

        self.assertContains(response, "Class Teacher")
        form = response.context["form"]
        self.assertIn(self.teacher, form.fields["class_teacher"].queryset)
        self.assertNotIn(self.admin, form.fields["class_teacher"].queryset)
        self.assertNotIn(self.student_parent, form.fields["class_teacher"].queryset)

        response = self.client.post(
            reverse("classes:create"),
            {"name": "Teacher Class", "class_teacher": self.teacher.pk},
        )

        self.assertEqual(response.status_code, 302)
        academic_class = AcademicClass.objects.get(name="Teacher Class")
        self.assertEqual(academic_class.class_teacher, self.teacher)

    def test_editing_class_displays_and_changes_teacher(self):
        replacement_teacher = User.objects.create_user(
            username="replacement-teacher",
            password="test-password-123",
            role=User.Role.TEACHER,
        )
        academic_class = AcademicClass.objects.create(
            name="Editable Class",
            class_teacher=self.teacher,
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("classes:update", args=[academic_class.pk])
        )

        self.assertEqual(
            response.context["form"].initial["class_teacher"],
            self.teacher.pk,
        )
        self.assertContains(response, self.teacher.get_username())

        response = self.client.post(
            reverse("classes:update", args=[academic_class.pk]),
            {"name": "Editable Class", "class_teacher": replacement_teacher.pk},
        )

        self.assertEqual(response.status_code, 302)
        academic_class.refresh_from_db()
        self.assertEqual(academic_class.class_teacher, replacement_teacher)

    def test_model_rejects_non_teacher_class_teacher(self):
        academic_class = AcademicClass(
            name="Invalid Teacher Class",
            class_teacher=self.student_parent,
        )

        with self.assertRaisesMessage(
            ValidationError,
            "The class teacher must have the Teacher role.",
        ):
            academic_class.full_clean()

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
        self.assertEqual(student.class_name, "Grade 10")

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

    def test_header_only_file_is_rejected_without_writes(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:import"),
            {
                "file": SimpleUploadedFile(
                    "header-only.csv",
                    b"name,class,section,roll_number,contact_details\n",
                    content_type="text/csv",
                )
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "does not contain any student records", status_code=400)
        self.assertEqual(Student.objects.count(), 0)

    def test_malformed_excel_file_is_rejected_without_writes(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:import"),
            {
                "file": SimpleUploadedFile(
                    "malformed.xlsx",
                    b"not an Excel workbook",
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Excel file could not be read", status_code=400)
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
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Row 2")
        self.assertContains(response, "roll number must be a positive whole number")
        self.assertEqual(Student.objects.count(), 0)

    def test_duplicate_roll_numbers_are_skipped_and_reported(self):
        existing = Student.objects.create(
            name="Existing Student",
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

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Row 3")
        self.assertContains(response, "duplicated in the file")
        self.assertEqual(Student.objects.count(), 2)
        self.assertTrue(Student.objects.filter(pk=existing.pk).exists())
        self.assertTrue(Student.objects.filter(roll_number=105).exists())

    def test_missing_required_row_is_skipped_while_valid_rows_are_saved(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:import"),
            {
                "file": self.csv_file(
                    [
                        {
                            "name": "Missing Contact",
                            "class": "Grade 10",
                            "section": "A",
                            "roll_number": "108",
                            "contact_details": " ",
                        },
                        {
                            "name": "Valid Student",
                            "class": "Grade 10",
                            "section": "A",
                            "roll_number": "109",
                            "contact_details": "valid@example.com",
                        },
                    ],
                    name="partial.csv",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Row 2")
        self.assertContains(response, "contact details is required")
        self.assertEqual(Student.objects.count(), 1)
        self.assertTrue(Student.objects.filter(roll_number=109).exists())

    def test_multiple_invalid_rows_report_physical_file_rows(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:import"),
            {
                "file": self.csv_file(
                    [
                        {
                            "name": "",
                            "class": "Grade 10",
                            "section": "A",
                            "roll_number": "110",
                            "contact_details": "missing-name@example.com",
                        },
                        {
                            "name": "Bad Roll",
                            "class": "Grade 10",
                            "section": "A",
                            "roll_number": "not-a-number",
                            "contact_details": "bad-roll@example.com",
                        },
                    ],
                    name="multiple-invalid.csv",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Row 2")
        self.assertContains(response, "Row 3")
        self.assertContains(response, "name is required")
        self.assertContains(response, "roll number must be a positive whole number")

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

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "was not found")
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


class StudentSectionRequiredTests(TestCase):
    """Issue #78: every student needs a section so they appear in attendance."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="section-admin", password="adminpass123", role=User.Role.ADMIN
        )
        self.teacher = User.objects.create_user(
            username="section-teacher", password="teacherpass123", role=User.Role.TEACHER
        )
        self.academic_class = AcademicClass.objects.create(
            name="Grade 5", class_teacher=self.teacher
        )
        self.section = Section.objects.create(academic_class=self.academic_class, name="A")

    def student_data(self, **overrides):
        data = {
            "name": "New Pupil",
            "section": self.section.pk,
            "roll_number": 501,
            "contact_details": "parent@example.com",
        }
        data.update(overrides)
        return data

    def import_csv(self, content):
        self.client.force_login(self.admin)
        return self.client.post(
            reverse("students:import"),
            {"file": SimpleUploadedFile("students.csv", content, content_type="text/csv")},
        )

    def test_saving_a_student_without_a_section_fails_with_a_clear_error(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:create"),
            self.student_data(section=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, Student.MISSING_SECTION_MESSAGE)
        self.assertFalse(Student.objects.filter(roll_number=501).exists())

    def test_removing_the_section_from_an_existing_student_is_rejected(self):
        student = Student.objects.create(
            name="Pupil", roll_number=502,
            contact_details="office", section=self.section,
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:update", args=[student.pk]),
            self.student_data(section="", roll_number=502),
        )

        self.assertContains(response, Student.MISSING_SECTION_MESSAGE)
        student.refresh_from_db()
        self.assertEqual(student.section, self.section)

    def test_model_validation_requires_a_section(self):
        student = Student(
            name="Pupil", roll_number=503, contact_details="office"
        )
        with self.assertRaises(ValidationError) as caught:
            student.full_clean()
        self.assertEqual(
            caught.exception.message_dict["section"], [Student.MISSING_SECTION_MESSAGE]
        )

    def test_student_saved_with_a_section_appears_on_mark_attendance(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("students:create"), self.student_data())
        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(roll_number=501)
        self.assertEqual(student.class_name, "Grade 5")

        self.client.force_login(self.teacher)
        page = self.client.get(
            reverse("pages:mark_attendance"), {"class": self.academic_class.pk}
        )
        self.assertContains(page, "New Pupil")

    def test_csv_row_without_a_section_is_rejected(self):
        response = self.import_csv(
            b"name,class,section,roll_number,contact_details\n"
            b"No Section,Grade 5,,601,office\n"
            b"Has Section,Grade 5,A,602,office\n"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Row 2: section is required.")
        self.assertFalse(Student.objects.filter(roll_number=601).exists())
        self.assertEqual(Student.objects.get(roll_number=602).section, self.section)

    def test_csv_without_a_section_column_is_rejected(self):
        response = self.import_csv(
            b"name,class,roll_number,contact_details\nNo Section,Grade 5,603,office\n"
        )

        self.assertContains(
            response, "Required columns are missing: section.", status_code=400
        )
        self.assertFalse(Student.objects.exists())

    def test_admin_sees_existing_students_without_a_section(self):
        orphan = Student.objects.create(
            name="Orphan Pupil", roll_number=504,
            contact_details="office",
        )
        Student.objects.create(
            name="Placed Pupil", roll_number=505,
            contact_details="office", section=self.section,
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("students:list"))

        self.assertEqual(list(response.context["students_without_section"]), [orphan])
        self.assertContains(response, "1 student without a section")
        self.assertContains(response, reverse("students:update", args=[orphan.pk]))

    def test_section_warning_is_hidden_when_every_student_has_a_section(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("students:list"))
        self.assertNotContains(response, "without a section")

    def test_teachers_do_not_see_the_admin_section_warning(self):
        Student.objects.create(
            name="Orphan Pupil", roll_number=506,
            contact_details="office",
        )
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("students:list"))
        self.assertNotContains(response, "without a section")


class ClassComesFromSectionTests(TestCase):
    """Issue #80: the class is always taken from the student's section."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="class-admin", password="adminpass123", role=User.Role.ADMIN
        )
        self.teacher = User.objects.create_user(
            username="class-teacher", password="teacherpass123", role=User.Role.TEACHER
        )
        self.parent = User.objects.create_user(
            username="class-parent", password="parentpass123", role=User.Role.STUDENT_PARENT
        )
        self.grade_4 = AcademicClass.objects.create(name="Grade 4", class_teacher=self.teacher)
        self.section_b = Section.objects.create(academic_class=self.grade_4, name="B")
        self.student = Student.objects.create(
            name="Mira Rao",
            roll_number=401,
            contact_details="office",
            section=self.section_b,
            parent=self.parent,
        )

    def test_form_and_model_no_longer_have_a_typed_class_field(self):
        from .forms import StudentForm

        self.assertNotIn("student_class", StudentForm().fields)
        self.assertNotIn("student_class", [f.name for f in Student._meta.get_fields()])
        self.client.force_login(self.admin)
        page = self.client.get(reverse("students:create"))
        self.assertNotContains(page, 'name="student_class"')

    def test_typed_class_sent_by_a_form_post_is_ignored(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:create"),
            {
                "name": "New Pupil",
                "student_class": "Grade 99",
                "section": self.section_b.pk,
                "roll_number": 402,
                "contact_details": "office",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Student.objects.get(roll_number=402).class_name, "Grade 4")

    def test_moving_section_changes_the_class_everywhere(self):
        grade_5 = AcademicClass.objects.create(name="Grade 5")
        section = Section.objects.create(academic_class=grade_5, name="A")
        self.student.section = section
        self.student.save()
        self.assertEqual(self.student.class_name, "Grade 5")

    def test_student_list_and_detail_show_the_class_from_the_section(self):
        self.client.force_login(self.admin)
        listing = self.client.get(reverse("students:list"))
        self.assertContains(listing, "Mira Rao - Grade 4 (B) - Roll 401")
        detail = self.client.get(reverse("students:detail", args=[self.student.pk]))
        self.assertContains(detail, '<dd class="col-sm-9">Grade 4</dd>', html=True)
        self.assertContains(detail, '<dd class="col-sm-9">B</dd>', html=True)

    def test_reports_show_the_class_from_the_section(self):
        self.client.force_login(self.parent)
        history = self.client.get(f"/api/attendance/student/{self.student.pk}")
        self.assertEqual(history.json()["student"]["className"], "Grade 4")

        workbook = load_workbook(
            BytesIO(
                self.client.get(
                    "/api/attendance/reports/student/excel",
                    {"studentId": self.student.pk},
                ).content
            )
        )
        rows = list(workbook["Attendance history"].iter_rows(values_only=True))
        self.assertIn(("Class", "Grade 4"), [row[:2] for row in rows])

        my_page = self.client.get(reverse("pages:my_attendance"))
        self.assertContains(my_page, "Mira Rao (Grade 4)")

    def test_csv_import_takes_the_class_from_the_section(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("students:import"),
            {
                "file": SimpleUploadedFile(
                    "students.csv",
                    b"name,class,section,roll_number,contact_details\n"
                    b"Imported Pupil,grade 4,b,403,office\n",
                    content_type="text/csv",
                )
            },
        )
        self.assertEqual(response.status_code, 302)
        imported = Student.objects.get(roll_number=403)
        self.assertEqual(imported.section, self.section_b)
        self.assertEqual(imported.class_name, "Grade 4")
