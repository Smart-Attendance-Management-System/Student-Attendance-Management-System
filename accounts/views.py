import json

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import UserAccountForm
from .models import User
from .permissions import IsAdmin


def _admin_required(view_func):
    @login_required(login_url="login")
    def wrapped(request, *args, **kwargs):
        if not IsAdmin().has_permission(request, view_func):
            return HttpResponseForbidden("Only admins can manage user accounts.")
        return view_func(request, *args, **kwargs)

    wrapped.__name__ = view_func.__name__
    return wrapped


@_admin_required
def user_list(request):
    return render(
        request,
        "accounts/user_list.html",
        {"users": User.objects.order_by("username")},
    )


@_admin_required
def user_create(request):
    form = UserAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "User account created successfully.")
        return redirect("accounts:list")
    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "title": "Create User"},
    )


@_admin_required
def user_update(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = UserAccountForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "User account updated successfully.")
        return redirect("accounts:list")
    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "title": "Edit User", "account": user},
    )


@_admin_required
@require_POST
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    user.delete()
    messages.success(request, "User account deleted successfully.")
    return redirect("accounts:list")


@require_POST
def login_api(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"status": "error", "message": "Request body must be valid JSON."},
            status=400,
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {"status": "error", "message": "A JSON object is required."},
            status=400,
        )

    username = data.get("username")
    password = data.get("password")
    if (
        not isinstance(username, str)
        or not username
        or not isinstance(password, str)
        or not password
    ):
        return JsonResponse(
            {"status": "error", "message": "Username and password are required."},
            status=400,
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse(
            {"status": "error", "message": "Invalid username or password."},
            status=401,
        )

    login(request, user)
    return JsonResponse(
        {
            "status": "success",
            "role": user.role,
            "session_token": request.session.session_key,
        }
    )
