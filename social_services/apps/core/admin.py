from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'department_type', 'is_mercy']
    list_filter = ['department_type', 'is_mercy']
    list_editable = ['department_type']
    search_fields = ['name', 'code']


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'get_full_name', 'role', 'department', 'is_active']
    list_filter = ['role', 'department', 'is_active', 'is_staff']
    search_fields = ['username', 'first_name', 'last_name', 'patronymic']
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Личная информация'), {'fields': ('first_name', 'patronymic', 'last_name', 'email')}),
        (_('Роль и отделение'), {'fields': ('role', 'department')}),
        (_('Права доступа'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Важные даты'), {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'patronymic', 'last_name', 'role', 'department', 'password1', 'password2'),
        }),
    )
