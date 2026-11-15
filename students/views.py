from django.contrib import messages
import logging
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import User
from accounts.permissions import IsAdmin, IsTeacher
from .bulk_import import BulkImportError, import_students
from .forms import AcademicClassForm, SectionForm, StudentForm, SubjectForm
from .models import AcademicClass, Section, Student, Subject

logger = logging.getLogger("sams.students")


def _admin_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not IsAdmin().has_permission(request, view_func):
            raise PermissionDenied("Only admins can manage these records.")
        return view_func(request, *args, **kwargs)

    wrapped.__name__ = view_func.__name__
    return wrapped


def _admin_or_teacher_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not (
            IsAdmin().has_permission(request, view_func)
            or IsTeacher().has_permission(request, view_func)
        ):
            raise PermissionDenied("Only admins and teachers can view students.")
        return view_func(request, *args, **kwargs)

    wrapped.__name__ = view_func.__name__
    return wrapped


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET", "POST"])
def student_create(request):
    if request.method == "POST":
        form = StudentForm(request.POST)
        if form.is_valid():
            try:
                student = form.save()
            except IntegrityError:
                form.add_error("roll_number", "A student with this roll number already exists.")
            else:
                logger.info("Student created user_id=%s student_id=%s", request.user.pk, student.pk)
                messages.success(request, "Student profile created successfully.")
                return redirect("students:list")
        return render(request, "students/student_form.html", {"form": form, "student": form.instance})

    return render(
        request,
        "students/student_form.html",
        {"form": StudentForm(), "student": Student()},
    )


# Present and Late both count as attended, the same rule as the attendance reports.
COUNTED_AS_PRESENT = ("Present", "Late")

SORT_OPTIONS = [
    ("roll", "Roll number"),
    ("name", "Name (A to Z)"),
    ("pct_low", "Attendance % (lowest first)"),
    ("pct_high", "Attendance % (highest first)"),
]


def with_attendance(queryset):
    """Add total_days and present_days to each student in the queryset."""
    return queryset.annotate(
        total_days=Count("attendance_records", distinct=True),
        present_days=Count(
            "attendance_records",
            filter=Q(attendance_records__status__in=COUNTED_AS_PRESENT),
            distinct=True,
        ),
    )


def add_percentage(students):
    """Set student.percentage (None when no attendance has been marked yet)."""
    for student in students:
        student.percentage = (
            round(student.present_days * 100 / student.total_days, 1)
            if student.total_days
            else None
        )
    return students


def sort_students(students, sort):
    if sort == "name":
        return sorted(students, key=lambda s: s.name.lower())
    if sort in ("pct_low", "pct_high"):
        marked = [s for s in students if s.percentage is not None]
        unmarked = [s for s in students if s.percentage is None]
        marked.sort(key=lambda s: s.percentage, reverse=(sort == "pct_high"))
        return marked + unmarked
    return sorted(students, key=lambda s: s.roll_number)


@login_required(login_url="login")
@_admin_or_teacher_required
@require_http_methods(["GET"])
def student_list(request):
    students = Student.objects.select_related("section__academic_class", "parent")
    classes = AcademicClass.objects.order_by("name")

    class_id = request.GET.get("class", "")
    section_id = request.GET.get("section", "")
    sort = request.GET.get("sort", "roll")
    if sort not in dict(SORT_OPTIONS):
        sort = "roll"

    sections = Section.objects.none()
    if class_id.isdigit():
        students = students.filter(section__academic_class_id=int(class_id))
        sections = Section.objects.filter(academic_class_id=int(class_id)).order_by("name")
        if section_id.isdigit():
            students = students.filter(section_id=int(section_id))

    student_rows = sort_students(add_percentage(list(with_attendance(students))), sort)
    context = {
        "students": student_rows,
        "classes": classes,
        "sections": sections,
        "selected_class": class_id,
        "selected_section": section_id,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
    }
    if request.user.role == User.Role.ADMIN:
        # Students without a section never appear on Mark attendance (issue #78).
        context["students_without_section"] = Student.objects.filter(section__isnull=True)
    return render(request, "students/student_list.html", context)


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET"])
def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    return render(request, "students/student_detail.html", {"student": student})


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET", "POST"])
def student_update(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error("roll_number", "A student with this roll number already exists.")
            else:
                logger.info("Student updated user_id=%s student_id=%s", request.user.pk, student.pk)
                messages.success(request, "Student profile updated successfully.")
                return redirect("students:list")
        return render(request, "students/student_form.html", {"form": form, "student": form.instance})

    return render(
        request,
        "students/student_form.html",
        {"form": StudentForm(instance=student), "student": student},
    )


@login_required(login_url="login")
@_admin_required
@require_http_methods(["POST"])
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    student.delete()
    logger.info("Student deleted user_id=%s student_id=%s", request.user.pk, pk)
    messages.success(request, "Student profile deleted successfully.")
    return redirect("students:list")


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET", "POST"])
def student_bulk_import(request):
    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return render(
                request,
                "students/student_import.html",
                {"error": "Select a CSV or .xlsx file to upload."},
            )
        try:
            import_result = import_students(uploaded_file)
        except BulkImportError as exc:
            return render(
                request,
                "students/student_import.html",
                {"error": str(exc)},
                status=400,
            )
        if import_result["failures"]:
            logger.warning(
                "Student import completed with rejected rows user_id=%s imported_count=%s failure_count=%s",
                request.user.pk,
                import_result["imported_count"],
                len(import_result["failures"]),
            )
            return render(
                request,
                "students/student_import.html",
                {"import_result": import_result},
            )
        messages.success(
            request,
            f"{import_result['imported_count']} student profiles imported successfully.",
        )
        logger.info(
            "Student import completed user_id=%s imported_count=%s",
            request.user.pk,
            import_result["imported_count"],
        )
        return redirect("students:list")
    return render(request, "students/student_import.html")


def _catalog_views(model, form_class, title, list_name):
    @login_required(login_url="login")
    @_admin_required
    @require_http_methods(["GET", "POST"])
    def create(request):
        form = form_class(request.POST or None)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error(None, f"{title} already exists.")
            else:
                logger.info(
                    "%s created user_id=%s record_id=%s",
                    title,
                    request.user.pk,
                    form.instance.pk,
                )
                messages.success(request, f"{title} created successfully.")
                return redirect(list_name)
        return render(
            request,
            "students/catalog_form.html",
            {"form": form, "title": f"Create {title}"},
        )

    @login_required(login_url="login")
    @_admin_required
    @require_http_methods(["GET"])
    def listing(request):
        return render(
            request,
            "students/catalog_list.html",
            {
                "records": model.objects.all(),
                "title": "Classes" if title == "Class" else f"{title}s",
                "create_url": f"{list_name.split(':')[0]}:create",
                "detail_url": f"{list_name.split(':')[0]}:detail",
                "update_url": f"{list_name.split(':')[0]}:update",
                "delete_url": f"{list_name.split(':')[0]}:delete",
            },
        )

    @login_required(login_url="login")
    @_admin_required
    @require_http_methods(["GET"])
    def detail(request, pk):
        return render(
            request,
            "students/catalog_detail.html",
            {"record": get_object_or_404(model, pk=pk), "title": title, "list_url": list_name},
        )

    @login_required(login_url="login")
    @_admin_required
    @require_http_methods(["GET", "POST"])
    def update(request, pk):
        record = get_object_or_404(model, pk=pk)
        form = form_class(request.POST or None, instance=record)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error(None, f"{title} already exists.")
            else:
                logger.info(
                    "%s updated user_id=%s record_id=%s",
                    title,
                    request.user.pk,
                    record.pk,
                )
                messages.success(request, f"{title} updated successfully.")
                return redirect(list_name)
        return render(
            request,
            "students/catalog_form.html",
            {"form": form, "title": f"Update {title}"},
        )

    @login_required(login_url="login")
    @_admin_required
    @require_http_methods(["POST"])
    def delete(request, pk):
        record = get_object_or_404(model, pk=pk)
        try:
            record.delete()
        except ProtectedError:
            messages.error(request, f"{title} cannot be deleted while it is in use.")
        else:
            logger.info("%s deleted user_id=%s record_id=%s", title, request.user.pk, pk)
            messages.success(request, f"{title} deleted successfully.")
        return redirect(list_name)

    return create, listing, detail, update, delete


class_views = _catalog_views(
    AcademicClass,
    AcademicClassForm,
    "Class",
    "classes:list",
)
section_views = _catalog_views(
    Section,
    SectionForm,
    "Section",
    "sections:list",
)
subject_views = _catalog_views(
    Subject,
    SubjectForm,
    "Subject",
    "subjects:list",
)

(
    academic_class_create,
    academic_class_list,
    academic_class_detail,
    academic_class_update,
    academic_class_delete,
) = class_views
(
    section_create,
    section_list,
    section_detail,
    section_update,
    section_delete,
) = section_views
(
    subject_create,
    subject_list,
    subject_detail,
    subject_update,
    subject_delete,
) = subject_views


# Classes -> sections -> students
# A class page lists its sections, and a section page lists its students, so there
# is no separate Sections menu item any more.


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET"])
def academic_class_list(request):
    classes = (
        AcademicClass.objects.select_related("class_teacher")
        .annotate(
            section_count=Count("sections", distinct=True),
            student_count=Count("sections__students", distinct=True),
        )
        .order_by("name")
    )
    return render(request, "students/class_list.html", {"classes": classes})


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET"])
def academic_class_detail(request, pk):
    academic_class = get_object_or_404(
        AcademicClass.objects.select_related("class_teacher"), pk=pk
    )
    sections = academic_class.sections.annotate(student_count=Count("students")).order_by("name")
    students = add_percentage(
        list(
            with_attendance(
                Student.objects.filter(section__academic_class=academic_class)
                .select_related("section")
                .order_by("roll_number")
            )
        )
    )
    return render(
        request,
        "students/class_detail.html",
        {"academic_class": academic_class, "sections": sections, "students": students},
    )


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET"])
def section_list(request):
    # Sections are now managed from each class's page
    return redirect("classes:list")


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET"])
def section_detail(request, pk):
    section = get_object_or_404(Section.objects.select_related("academic_class"), pk=pk)
    students = add_percentage(
        list(with_attendance(section.students.select_related("parent").order_by("roll_number")))
    )
    return render(
        request,
        "students/section_detail.html",
        {"section": section, "students": students},
    )


def _section_form_page(request, form, title):
    return render(request, "students/catalog_form.html", {"form": form, "title": title})


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET", "POST"])
def section_create(request):
    initial = {}
    class_id = request.GET.get("class", "")
    if class_id.isdigit():
        initial["academic_class"] = int(class_id)
    form = SectionForm(request.POST or None, initial=initial)
    if form.is_valid():
        try:
            section = form.save()
        except IntegrityError:
            form.add_error(None, "Section already exists.")
        else:
            logger.info("Section created user_id=%s record_id=%s", request.user.pk, section.pk)
            messages.success(request, "Section created successfully.")
            return redirect("classes:detail", pk=section.academic_class_id)
    return _section_form_page(request, form, "Create Section")


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET", "POST"])
def section_update(request, pk):
    section = get_object_or_404(Section, pk=pk)
    form = SectionForm(request.POST or None, instance=section)
    if form.is_valid():
        try:
            form.save()
        except IntegrityError:
            form.add_error(None, "Section already exists.")
        else:
            logger.info("Section updated user_id=%s record_id=%s", request.user.pk, section.pk)
            messages.success(request, "Section updated successfully.")
            return redirect("classes:detail", pk=section.academic_class_id)
    return _section_form_page(request, form, "Update Section")


@login_required(login_url="login")
@_admin_required
@require_http_methods(["POST"])
def section_delete(request, pk):
    section = get_object_or_404(Section, pk=pk)
    class_id = section.academic_class_id
    try:
        section.delete()
    except ProtectedError:
        messages.error(request, "Section cannot be deleted while it is in use.")
    else:
        logger.info("Section deleted user_id=%s record_id=%s", request.user.pk, pk)
        messages.success(request, "Section deleted successfully.")
    return redirect("classes:detail", pk=class_id)