from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("users/", views.user_list, name="list"),
    path("users/create/", views.user_create, name="create"),
    path("users/<int:pk>/edit/", views.user_update, name="update"),
    path("users/<int:pk>/delete/", views.user_delete, name="delete"),
]
