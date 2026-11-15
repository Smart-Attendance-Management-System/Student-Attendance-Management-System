"""Issue #80: removing the typed class name must keep existing data safe."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("students", "0004_student_parent")]
AFTER = [("students", "0005_remove_student_student_class")]


class RemoveStudentClassMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def setUp(self):
        old_apps = self.migrate(BEFORE)
        AcademicClass = old_apps.get_model("students", "AcademicClass")
        Section = old_apps.get_model("students", "Section")
        self.Student = old_apps.get_model("students", "Student")

        grade_1 = AcademicClass.objects.create(name="Grade 1")
        self.grade_1_a = Section.objects.create(academic_class=grade_1, name="A")
        grade_2 = AcademicClass.objects.create(name="Grade 2")
        self.grade_2_a = Section.objects.create(academic_class=grade_2, name="A")
        Section.objects.create(academic_class=grade_2, name="B")

        self.Student.objects.create(
            name="Has Section", student_class="Grade 1", roll_number=1,
            contact_details="x", section_id=self.grade_1_a.pk,
        )
        self.Student.objects.create(
            name="Typed Only", student_class="  grade 1 ", roll_number=2,
            contact_details="x",
        )

    def tearDown(self):
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM students_student")
        self.migrate(self.latest())

    def latest(self):
        executor = MigrationExecutor(connection)
        return executor.loader.graph.leaf_nodes()

    def test_students_with_one_possible_section_are_placed_in_it(self):
        new_apps = self.migrate(AFTER)
        Student = new_apps.get_model("students", "Student")

        self.assertEqual(
            dict(Student.objects.values_list("roll_number", "section_id")),
            {1: self.grade_1_a.pk, 2: self.grade_1_a.pk},
        )

    def test_migration_stops_without_changes_when_a_section_is_unclear(self):
        self.Student.objects.create(
            name="Two Sections", student_class="Grade 2", roll_number=3, contact_details="x",
        )
        self.Student.objects.create(
            name="Unknown Class", student_class="Grade 99", roll_number=4, contact_details="x",
        )

        with self.assertRaises(RuntimeError) as caught:
            self.migrate(AFTER)

        message = str(caught.exception)
        self.assertIn("Two Sections (roll 3, class 'Grade 2')", message)
        self.assertIn("Unknown Class (roll 4, class 'Grade 99')", message)
        self.assertNotIn("Typed Only", message)
        # Nothing changed: the typed class column and the missing section are both kept.
        self.assertEqual(
            dict(self.Student.objects.values_list("roll_number", "student_class")),
            {1: "Grade 1", 2: "  grade 1 ", 3: "Grade 2", 4: "Grade 99"},
        )
        self.assertIsNone(self.Student.objects.get(roll_number=2).section_id)

    def test_migration_can_be_reversed(self):
        self.migrate(AFTER)
        old_apps = self.migrate(BEFORE)
        Student = old_apps.get_model("students", "Student")
        self.assertEqual(
            dict(Student.objects.values_list("roll_number", "student_class")),
            {1: "Grade 1", 2: "Grade 1"},
        )
