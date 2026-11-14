import re
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from students.models import AcademicClass, Section, Student

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
        response = self.client.get(reverse("pages:student_list"))
        self.assertRedirects(response, reverse("students:list"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("students:list")).status_code, 200)
        response = self.client.get(reverse("pages:mark_attendance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mark attendance")

    def test_admin_can_open_student_list(self):
        self.client.force_login(self.make_user(User.Role.ADMIN))
        response = self.client.get(reverse("pages:student_list"))
        self.assertRedirects(response, reverse("students:list"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("students:list")).status_code, 200)

    def test_admin_is_redirected_from_mark_attendance(self):
        self.client.force_login(self.make_user(User.Role.ADMIN))
        response = self.client.get(reverse("pages:mark_attendance"))
        self.assertRedirects(response, reverse("pages:home"), fetch_redirect_response=False)

    def test_student_parent_is_redirected_from_both_pages(self):
        self.client.force_login(self.make_user(User.Role.STUDENT_PARENT))
        for name in ("pages:student_list", "pages:mark_attendance"):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, reverse("pages:home"), fetch_redirect_response=False)

    def test_student_list_urls_share_canonical_route(self):
        admin = self.make_user(User.Role.ADMIN)
        self.client.force_login(admin)

        legacy_response = self.client.get(reverse("pages:student_list"))
        self.assertRedirects(
            legacy_response,
            reverse("students:list"),
            fetch_redirect_response=False,
        )
        canonical_response = self.client.get(reverse("students:list"))
        self.assertEqual(canonical_response.status_code, 200)
        self.assertContains(canonical_response, "Student Profiles")
        self.assertNotContains(canonical_response, "Subjects")

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

    def test_daily_page_includes_attendance_edit_control(self):
        teacher = self.make_user(User.Role.TEACHER)
        AcademicClass.objects.create(name="Grade 10", class_teacher=teacher)
        self.client.force_login(teacher)
        response = self.client.get(reverse("pages:daily_attendance"))
        self.assertContains(response, "Edit attendance")
        self.assertContains(response, 'id="editForm"')

    def test_staff_user_sees_link_to_admin_site(self):
        self.client.force_login(self.make_user(User.Role.ADMIN, is_staff=True))
        response = self.client.get(reverse("students:list"))
        self.assertContains(response, reverse("admin:index"))
        self.assertContains(response, "Admin site")

    def test_login_page_links_to_admin_site(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, reverse("admin:index"))


class AttendanceSummaryPageTests(TestCase):
    def make_user(self, role):
        return User.objects.create_user(
            username=role.lower(), password="test-password", role=role
        )

    def test_admin_can_open_summary_page(self):
        self.client.force_login(self.make_user(User.Role.ADMIN))
        response = self.client.get(reverse("pages:attendance_summary"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attendance summaries")
        self.assertContains(response, 'id="startDate"')
        self.assertContains(response, 'id="endDate"')

    def test_non_admin_users_cannot_open_summary_page(self):
        for role in (User.Role.TEACHER, User.Role.STUDENT_PARENT):
            with self.subTest(role=role):
                self.client.force_login(self.make_user(role))
                response = self.client.get(reverse("pages:attendance_summary"))
                self.assertRedirects(
                    response,
                    reverse("pages:home"),
                    fetch_redirect_response=False,
                )

    def test_admin_navigation_link_is_not_shown_to_teacher(self):
        teacher = self.make_user(User.Role.TEACHER)
        self.client.force_login(teacher)
        response = self.client.get(reverse("pages:mark_attendance"))
        self.assertNotContains(response, "Attendance summaries")


class MyAttendancePageTests(TestCase):
    def make_parent(self, username="parent1"):
        return User.objects.create_user(
            username=username, password="pass12345", role=User.Role.STUDENT_PARENT
        )

    def make_child(self, parent, name="Asha Rao"):
        section = Section.objects.create(
            academic_class=AcademicClass.objects.create(name="Grade 10"), name="A"
        )
        return Student.objects.create(
            name=name, student_class="Grade 10", roll_number=1,
            contact_details="asha@example.com", section=section, parent=parent,
        )

    def test_parent_sees_their_child_on_the_page(self):
        parent = self.make_parent()
        self.make_child(parent)
        self.client.force_login(parent)
        response = self.client.get(reverse("pages:my_attendance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My attendance")
        self.assertContains(response, "Asha Rao")

    def test_parent_with_no_linked_child_sees_a_clear_message(self):
        self.client.force_login(self.make_parent())
        response = self.client.get(reverse("pages:my_attendance"))
        self.assertContains(response, "No student is linked to your account")

    def test_parent_does_not_see_other_parents_children(self):
        self.make_child(self.make_parent("parent2"), name="Someone Else")
        mine = self.make_parent("parent1")
        self.client.force_login(mine)
        response = self.client.get(reverse("pages:my_attendance"))
        self.assertNotContains(response, "Someone Else")

    def test_home_sends_a_parent_to_the_attendance_page(self):
        self.client.force_login(self.make_parent())
        response = self.client.get(reverse("pages:home"))
        self.assertRedirects(
            response, reverse("pages:my_attendance"), fetch_redirect_response=False
        )

    def test_teacher_is_redirected_away_and_has_no_nav_link(self):
        teacher = User.objects.create_user(
            username="teacher1", password="pass12345", role=User.Role.TEACHER
        )
        self.client.force_login(teacher)
        response = self.client.get(reverse("pages:my_attendance"))
        self.assertRedirects(response, reverse("pages:home"), fetch_redirect_response=False)
        page = self.client.get(reverse("pages:mark_attendance"))
        self.assertNotContains(page, "My attendance")

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse("pages:my_attendance"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

class UsabilityCompatibilityTests(TestCase):
    """NFR4 / TC-12: automated part of the usability checks.

    The per-browser and per-device results are recorded manually on the
    issue; these tests stop the markup that makes those checks pass from
    regressing.
    """

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher1", password="pass12345", role=User.Role.TEACHER
        )
        self.admin = User.objects.create_user(
            username="admin1", password="pass12345", role=User.Role.ADMIN
        )
        self.parent = User.objects.create_user(
            username="parent1", password="pass12345", role=User.Role.STUDENT_PARENT
        )
        self.cls = AcademicClass.objects.create(name="Grade 6", class_teacher=self.teacher)
        section = Section.objects.create(academic_class=self.cls, name="A")
        self.students = [
            Student.objects.create(
                name=f"Pupil {n}", student_class="Grade 6", roll_number=500 + n,
                contact_details="office", section=section,
            )
            for n in range(1, 4)
        ]

    def pages_for(self, user):
        return {
            self.teacher: [
                reverse("pages:mark_attendance") + f"?class={self.cls.pk}",
                reverse("pages:daily_attendance"),
                reverse("students:list"),
            ],
            self.admin: [
                reverse("students:list"),
                reverse("pages:attendance_summary"),
                reverse("pages:daily_attendance"),
                reverse("accounts:list"),
            ],
            self.parent: [reverse("pages:my_attendance")],
        }[user]

    def test_every_role_page_is_mobile_ready(self):
        for user in (self.teacher, self.admin, self.parent):
            self.client.force_login(user)
            for url in self.pages_for(user):
                with self.subTest(user=user.username, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, 'name="viewport" content="width=device-width, initial-scale=1"')
                    # navigation collapses behind a menu button on narrow screens
                    self.assertContains(response, 'class="navbar navbar-expand-lg')
                    self.assertContains(response, 'class="navbar-toggler"')
                    self.assertContains(response, "bootstrap.bundle.min.js")

    def test_login_page_is_mobile_ready(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, 'name="viewport"')

    def test_marking_needs_at_most_one_tap_per_student(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("pages:mark_attendance") + f"?class={self.cls.pk}")
        html = response.content.decode()
        for student in self.students:
            with self.subTest(student=student.name):
                # Present is pre-selected (0 taps) and every other status is one tap away
                present_input = re.search(rf'<input[^>]*id="s{student.pk}-Present"[^>]*>', html)
                self.assertIsNotNone(present_input)
                self.assertRegex(present_input.group(0), r"\schecked\b")
                for status in ("Absent", "Late", "Excused"):
                    self.assertIn(f'for="s{student.pk}-{status}"', html)
                self.assertEqual(html.count(f'name="status-{student.pk}"'), 4)
        self.assertContains(response, 'id="markAll"')
        self.assertContains(response, 'class="submit-bar')

    def test_status_buttons_are_touch_sized(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("pages:mark_attendance") + f"?class={self.cls.pk}")
        self.assertContains(response, "min-height: 44px")
        self.assertNotContains(response, "btn-outline-primary btn-sm")

    def test_tables_scroll_inside_their_container(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("pages:mark_attendance") + f"?class={self.cls.pk}")
        self.assertContains(response, 'class="table-responsive"')
        self.client.force_login(self.admin)
        response = self.client.get(reverse("students:list"))
        self.assertContains(response, 'class="list-group list-group-flush"')



class TeacherDashboardTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher1", password="pass12345", role=User.Role.TEACHER
        )
        self.other = User.objects.create_user(
            username="teacher2", password="pass12345", role=User.Role.TEACHER
        )
        self.cls = AcademicClass.objects.create(name="Grade 10", class_teacher=self.teacher)
        section = Section.objects.create(academic_class=self.cls, name="A")
        self.students = [
            Student.objects.create(
                name=f"Student {n}", student_class="Grade 10", roll_number=n,
                contact_details=f"p{n}@example.com", section=section,
            )
            for n in (1, 2)
        ]
        AcademicClass.objects.create(name="Grade 9", class_teacher=self.other)

    def test_shows_only_the_teachers_own_classes(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("pages:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your classes today")
        self.assertContains(response, "Grade 10")
        self.assertNotContains(response, "Grade 9")
        self.assertNotContains(response, "coming soon")

    def test_unmarked_class_shows_mark_button(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("pages:home"))
        self.assertContains(response, "Not marked")
        self.assertContains(response, f"?class={self.cls.pk}")

    def test_marked_class_shows_marked_and_absent_count(self):
        from attendance import services

        services.mark_attendance(
            self.teacher, self.cls.pk, timezone.localdate().isoformat(),
            [{"studentId": self.students[0].pk, "status": "Absent"}],
        )
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("pages:home"))
        self.assertContains(response, "Marked")
        self.assertContains(response, "1 absent")
        self.assertNotContains(response, f"?class={self.cls.pk}")

    def test_class_with_no_students(self):
        AcademicClass.objects.create(name="Grade 8", class_teacher=self.teacher)
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("pages:home"))
        self.assertContains(response, "No students yet")

    def test_teacher_with_no_classes(self):
        lonely = User.objects.create_user(
            username="teacher3", password="pass12345", role=User.Role.TEACHER
        )
        self.client.force_login(lonely)
        response = self.client.get(reverse("pages:home"))
        self.assertContains(response, "No classes yet")


class PopupMessageTests(TestCase):
    """Messages show as a popup (toast) at the top instead of below the page."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher1", password="pass12345", role=User.Role.TEACHER
        )
        self.admin = User.objects.create_user(
            username="admin1", password="pass12345", role=User.Role.ADMIN
        )
        self.cls = AcademicClass.objects.create(name="Grade 7", class_teacher=self.teacher)
        section = Section.objects.create(academic_class=self.cls, name="A")
        Student.objects.create(
            name="Pupil", student_class="Grade 7", roll_number=1,
            contact_details="office", section=section,
        )

    def test_every_page_has_the_popup_area(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("pages:daily_attendance"))
        self.assertContains(response, 'id="toastArea"')
        self.assertContains(response, "function showToast(")

    def test_mark_attendance_result_is_a_popup(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("pages:mark_attendance") + f"?class={self.cls.pk}")
        self.assertContains(response, "showToast(kind, text)")
        self.assertNotContains(response, 'id="result"')

    def test_server_messages_show_as_a_popup(self):
        other = User.objects.create_user(
            username="spare", password="pass12345", role=User.Role.TEACHER
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:delete", args=[other.pk]), follow=True
        )
        self.assertContains(response, 'class="toast border-0 border-start border-4 border-success"')
        self.assertContains(response, "User account deleted successfully.")
        self.assertNotContains(response, 'class="alert alert-info"')

class MarkAttendanceClassListTests(TestCase):
    """Issue #77: Mark attendance only offers the teacher's own classes."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="own-teacher", password="pass12345", role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username="other-teacher", password="pass12345", role=User.Role.TEACHER
        )
        self.own_class = AcademicClass.objects.create(
            name="Grade 7", class_teacher=self.teacher
        )
        self.other_class = AcademicClass.objects.create(
            name="Grade 8", class_teacher=self.other_teacher
        )
        self.unassigned_class = AcademicClass.objects.create(name="Grade 9")
        for academic_class in (self.own_class, self.other_class):
            section = Section.objects.create(academic_class=academic_class, name="A")
            Student.objects.create(
                name=f"Pupil of {academic_class.name}",
                roll_number=700 + academic_class.pk,
                contact_details="office",
                section=section,
            )

    def test_teacher_only_sees_their_own_classes_in_the_dropdown(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("pages:mark_attendance"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["classes"]), [self.own_class])
        self.assertContains(response, f'value="{self.own_class.pk}"')
        self.assertNotContains(response, f'value="{self.other_class.pk}"')
        self.assertNotContains(response, f'value="{self.unassigned_class.pk}"')

    def test_dropdown_matches_the_daily_view_page(self):
        self.client.force_login(self.teacher)
        mark = self.client.get(reverse("pages:mark_attendance"))
        daily = self.client.get(reverse("pages:daily_attendance"))
        self.assertEqual(list(mark.context["classes"]), list(daily.context["classes"]))

    def test_another_teachers_class_cannot_be_opened_by_url(self):
        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse("pages:mark_attendance") + f"?class={self.other_class.pk}"
        )

        self.assertIsNone(response.context["selected"])
        self.assertEqual(list(response.context["students"]), [])
        self.assertNotContains(response, "Pupil of Grade 8")

    def test_teacher_without_classes_sees_a_message(self):
        lonely = User.objects.create_user(
            username="no-class-teacher", password="pass12345", role=User.Role.TEACHER
        )
        self.client.force_login(lonely)
        response = self.client.get(reverse("pages:mark_attendance"))
        self.assertContains(response, "You are not the class teacher of any class yet.")
