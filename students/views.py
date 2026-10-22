from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import User
from .bulk_import import BulkImportError, import_students
from .forms import AcademicClassForm, SectionForm, StudentForm, SubjectForm
from .models import AcademicClass, Section, Student, Subject


def _admin_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if request.user.role != User.Role.ADMIN:
            return HttpResponseForbidden("Only admins can manage these records.")
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
                messages.success(request, "Student profile created successfully.")
                return redirect("students:list")
        return render(request, "students/student_form.html", {"form": form, "student": form.instance})

    return render(
        request,
        "students/student_form.html",
        {"form": StudentForm(), "student": Student()},
    )


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET"])
def student_list(request):
    students = Student.objects.all()
    return render(request, "students/student_list.html", {"students": students})


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
            imported_count = import_students(uploaded_file)
        except BulkImportError as exc:
            return render(
                request,
                "students/student_import.html",
                {"error": str(exc)},
                status=400,
            )
        messages.success(request, f"{imported_count} student profiles imported successfully.")
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
                "title": f"{title}s",
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
