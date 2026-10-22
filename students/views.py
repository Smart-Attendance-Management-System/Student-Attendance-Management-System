from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import User
from .models import Student


def _admin_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if request.user.role != User.Role.ADMIN:
            return HttpResponseForbidden("Only admins can manage student profiles.")
        return view_func(request, *args, **kwargs)

    wrapped.__name__ = view_func.__name__
    return wrapped


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET", "POST"])
def student_create(request):
    if request.method == "POST":
        student = Student(
            name=request.POST.get("name", "").strip(),
            student_class=request.POST.get("student_class", "").strip(),
            roll_number=request.POST.get("roll_number", ""),
            contact_details=request.POST.get("contact_details", "").strip(),
        )
        try:
            student.full_clean()
            student.save()
            messages.success(request, "Student profile created successfully.")
            return redirect("students:list")
        except (ValidationError, ValueError) as exc:
            errors = exc.message_dict if hasattr(exc, "message_dict") else {"__all__": [str(exc)]}
            return render(request, "students/student_form.html", {"student": student, "errors": errors})
        except IntegrityError:
            return render(
                request,
                "students/student_form.html",
                {"student": student, "errors": {"roll_number": ["A student with this roll number already exists."]}},
            )

    return render(request, "students/student_form.html", {"student": Student()})


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
    student = Student.objects.get(pk=pk)
    return render(request, "students/student_detail.html", {"student": student})


@login_required(login_url="login")
@_admin_required
@require_http_methods(["GET", "POST"])
def student_update(request, pk):
    student = Student.objects.get(pk=pk)
    if request.method == "POST":
        student.name = request.POST.get("name", "").strip()
        student.student_class = request.POST.get("student_class", "").strip()
        student.roll_number = request.POST.get("roll_number", "")
        student.contact_details = request.POST.get("contact_details", "").strip()
        try:
            student.full_clean()
            student.save()
            messages.success(request, "Student profile updated successfully.")
            return redirect("students:list")
        except (ValidationError, ValueError) as exc:
            errors = exc.message_dict if hasattr(exc, "message_dict") else {"__all__": [str(exc)]}
            return render(request, "students/student_form.html", {"student": student, "errors": errors})
        except IntegrityError:
            return render(
                request,
                "students/student_form.html",
                {"student": student, "errors": {"roll_number": ["A student with this roll number already exists."]}},
            )

    return render(request, "students/student_form.html", {"student": student})


@login_required(login_url="login")
@_admin_required
@require_http_methods(["POST"])
def student_delete(request, pk):
    student = Student.objects.get(pk=pk)
    student.delete()
    messages.success(request, "Student profile deleted successfully.")
    return redirect("students:list")
