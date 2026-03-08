from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, Department, LocationType, Organization, Employee, SystemSettings


@admin.register(LocationType)
class LocationTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active_status', 'requires_department', 'order']
    list_editable = ['order']
    ordering = ['order']


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'department_type']
    list_filter = ['department_type']
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


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'inn', 'ogrn', 'phone', 'get_director_name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'short_name', 'inn', 'ogrn', 'director__last_name', 'director__first_name']
    list_editable = ['is_active']
    autocomplete_fields = ['director']
    
    def get_director_name(self, obj):
        if obj.director:
            return obj.director.get_full_name()
        return '-'
    get_director_name.short_description = 'Руководитель'


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['get_full_name', 'position', 'organization', 'phone', 'is_active']
    list_filter = ['is_active', 'organization', 'gender']
    search_fields = ['last_name', 'first_name', 'patronymic', 'position', 'phone', 'passport_series', 'passport_number']
    list_editable = ['is_active']
    raw_id_fields = ['user']
    
    fieldsets = (
        ('Персональные данные', {
            'fields': ('last_name', 'first_name', 'patronymic', 'gender', 'birth_date')
        }),
        ('Контактная информация', {
            'fields': ('phone', 'email')
        }),
        ('Трудовая информация', {
            'fields': ('position', 'organization', 'user')
        }),
        ('Адрес регистрации', {
            'fields': ('address',),
            'classes': ('collapse',),
        }),
        ('Паспортные данные', {
            'fields': ('passport_series', 'passport_number', 'passport_issued_by', 'passport_issue_date', 'passport_department_code'),
            'classes': ('collapse',),
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
    )
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = 'ФИО'


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    """Админка для настроек системы (singleton)"""
    
    fieldsets = (
        ('Исполнитель', {
            'fields': ('executor_organization', 'executor_signatory'),
            'description': 'Организация и сотрудник, подписывающий акты от имени исполнителя'
        }),
        ('Заказчик', {
            'fields': ('customer_organization', 'customer_signatory'),
            'description': 'Организация и сотрудник, подписывающий акты от имени заказчика'
        }),
    )
    
    autocomplete_fields = ['executor_organization', 'executor_signatory', 
                          'customer_organization', 'customer_signatory']
    
    def has_add_permission(self, request):
        # Запрещаем добавление - только одна запись
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Запрещаем удаление
        return False
    
    def changelist_view(self, request, extra_context=None):
        # Перенаправляем на страницу редактирования единственной записи
        from django.shortcuts import redirect
        obj = SystemSettings.get_settings()
        return redirect(f'/admin/core/systemsettings/{obj.pk}/change/')
