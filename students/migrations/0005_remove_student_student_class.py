"""Remove the typed class name from Student (issue #80).

A student's class now always comes from their section. Before the column is
dropped, every student without a section is placed in one when that can be
done safely: the typed class name matches an existing class (ignoring case
and surrounding spaces) and that class has exactly one section.

If any student still cannot be placed, the migration stops and changes
nothing, so no class information is lost. The admin then gives those
students a section on the Students page and runs migrate again.
"""

from django.db import migrations, models


def assign_missing_sections(apps, schema_editor):
    Student = apps.get_model("students", "Student")
    AcademicClass = apps.get_model("students", "AcademicClass")
    Section = apps.get_model("students", "Section")

    unresolved = []
    for student in Student.objects.filter(section__isnull=True).order_by("roll_number"):
        typed_class = (student.student_class or "").strip()
        academic_class = (
            AcademicClass.objects.filter(name__iexact=typed_class).first()
            if typed_class
            else None
        )
        sections = (
            list(Section.objects.filter(academic_class=academic_class)[:2])
            if academic_class
            else []
        )
        if len(sections) == 1:
            student.section = sections[0]
            student.save(update_fields=["section"])
        else:
            unresolved.append(
                f"  - {student.name} (roll {student.roll_number}, class '{typed_class}')"
            )

    if unresolved:
        raise RuntimeError(
            "These students have no section, and the right section could not be "
            "worked out from their typed class name:\n"
            + "\n".join(unresolved)
            + "\nGive each of them a section on the Students page, then run "
            "migrate again. No data was changed."
        )


def restore_class_names(apps, schema_editor):
    """Reverse: fill the re-added column from each student's section."""
    Student = apps.get_model("students", "Student")
    for student in Student.objects.select_related("section__academic_class"):
        if student.section_id:
            student.student_class = student.section.academic_class.name
            student.save(update_fields=["student_class"])


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0004_student_parent"),
    ]

    operations = [
        migrations.RunPython(assign_missing_sections, restore_class_names),
        migrations.AlterModelOptions(
            name="student",
            options={
                "ordering": ["section__academic_class__name", "section__name", "roll_number"],
                "verbose_name": "student profile",
                "verbose_name_plural": "student profiles",
            },
        ),
        # A default lets a rollback re-add the column before it is refilled.
        migrations.AlterField(
            model_name="student",
            name="student_class",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.RemoveField(
            model_name="student",
            name="student_class",
        ),
    ]
