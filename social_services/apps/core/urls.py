from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('departments/', views.departments_view, name='departments'),
    path('departments/<int:department_id>/print/', views.department_residents_print, name='department_residents_print'),
    path('departments/<int:department_id>/print-only/', views.department_residents_print_only, name='department_residents_print_only'),
]
