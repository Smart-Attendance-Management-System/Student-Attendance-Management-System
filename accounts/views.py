import json

from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.views.decorators.http import require_POST


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
