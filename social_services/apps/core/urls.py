from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('departments/', views.departments_view, name='departments'),
    path('departments/<int:department_id>/print/', views.department_residents_print, name='department_residents_print'),
    path('departments/<int:department_id>/print-only/', views.department_residents_print_only, name='department_residents_print_only'),
    # Исполнители
    path('executors/', RedirectView.as_view(pattern_name='organizations', permanent=False)),
    path('executors/organizations/', views.organization_list, name='organizations'),
    path('executors/organizations/<int:pk>/', views.organization_detail, name='organization_detail'),
    path('executors/employees/', views.employee_list, name='employees'),
    path('executors/employees/<int:pk>/', views.employee_detail, name='employee_detail'),
]
