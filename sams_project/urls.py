"""
URL configuration for sams_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from students import views as student_views

classes_urlpatterns = [
    path('', student_views.academic_class_list, name='list'),
    path('create/', student_views.academic_class_create, name='create'),
    path('<int:pk>/', student_views.academic_class_detail, name='detail'),
    path('<int:pk>/update/', student_views.academic_class_update, name='update'),
    path('<int:pk>/delete/', student_views.academic_class_delete, name='delete'),
]

sections_urlpatterns = [
    path('', student_views.section_list, name='list'),
    path('create/', student_views.section_create, name='create'),
    path('<int:pk>/', student_views.section_detail, name='detail'),
    path('<int:pk>/update/', student_views.section_update, name='update'),
    path('<int:pk>/delete/', student_views.section_delete, name='delete'),
]

subjects_urlpatterns = [
    path('', student_views.subject_list, name='list'),
    path('create/', student_views.subject_create, name='create'),
    path('<int:pk>/', student_views.subject_detail, name='detail'),
    path('<int:pk>/update/', student_views.subject_update, name='update'),
    path('<int:pk>/delete/', student_views.subject_delete, name='delete'),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('students/', include(([
        path('', student_views.student_list, name='list'),
        path('create/', student_views.student_create, name='create'),
        path('import/', student_views.student_bulk_import, name='import'),
        path('<int:pk>/', student_views.student_detail, name='detail'),
        path('<int:pk>/update/', student_views.student_update, name='update'),
        path('<int:pk>/delete/', student_views.student_delete, name='delete'),
    ], 'students'), 'students')),
    path('classes/', include((classes_urlpatterns, 'classes'), namespace='classes')),
    path('sections/', include((sections_urlpatterns, 'sections'), namespace='sections')),
    path('subjects/', include((subjects_urlpatterns, 'subjects'), namespace='subjects')),
    path('', include(('pages.urls', 'pages'), namespace='pages')),
]
