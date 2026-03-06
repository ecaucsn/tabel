from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Recipient, Contract, ContractService, RecipientHistory, MonthlyRecipientData


class ContractServiceInline(admin.TabularInline):
    model = ContractService
    extra = 1
    autocomplete_fields = ['service']
    fields = ['service']


class RecipientHistoryInline(admin.TabularInline):
    """Инлайн для отображения истории изменений в карточке получателя"""
    model = RecipientHistory
    extra = 0
    readonly_fields = ['change_type_display', 'old_department', 'new_department', 'old_room', 'new_room', 
                       'old_status', 'new_status', 'reason', 'date', 'changed_by', 'created_at']
    fields = ['change_type_display', 'old_department', 'new_department', 'old_room', 'new_room', 
              'old_status', 'new_status', 'reason', 'date', 'changed_by', 'created_at']
    
    def change_type_display(self, obj):
        return obj.change_type_display
    change_type_display.short_description = 'Тип изменения'
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Recipient)
class RecipientAdmin(admin.ModelAdmin):
    list_display = ['photo_preview', 'full_name', 'birth_date', 'department', 'room', 'status_display', 'age']
    list_filter = ['department']
    search_fields = ['last_name', 'first_name', 'patronymic']
    list_editable = ['room']
    date_hierarchy = 'admission_date'
    inlines = [RecipientHistoryInline]
    
    fieldsets = (
        ('Персональные данные', {
            'fields': ('photo', 'photo_preview_admin', 'last_name', 'first_name', 'patronymic', 'birth_date')
        }),
        ('Размещение', {
            'fields': ('department', 'room', 'admission_date', 'discharge_date')
        }),
    )
    
    readonly_fields = ['photo_preview_admin']
    
    def photo_preview(self, obj):
        """Превью фото в списке"""
        if obj and obj.photo:
            return format_html(
                '<img src="{}" style="width: 40px; height: 40px; object-fit: cover; border-radius: 50%;" />',
                obj.photo.url
            )
        return mark_safe(
            '<div style="width: 40px; height: 40px; background: #e2e8f0; border-radius: 50%; display: flex; align-items: center; justify-content: center;">'
            '<svg style="width: 20px; height: 20px; color: #94a3b8;" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>'
            '</svg></div>'
        )
    photo_preview.short_description = 'Фото'
    
    def photo_preview_admin(self, obj):
        """Превью фото в форме редактирования"""
        if obj and obj.photo:
            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 200px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);" />',
                obj.photo.url
            )
        return "Фотография не загружена"
    photo_preview_admin.short_description = 'Превью фотографии'
    
    def status_display(self, obj):
        """Отображение статуса"""
        status_colors = {
            'active': 'bg-green-100 text-green-800',
            'vacation': 'bg-yellow-100 text-yellow-800',
            'hospital': 'bg-blue-100 text-blue-800',
            'discharged': 'bg-red-100 text-red-800',
        }
        color = status_colors.get(obj.status, 'bg-gray-100 text-gray-800')
        return format_html(
            '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {}">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Статус'


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['number', 'recipient', 'date_start', 'date_end', 'is_active']
    list_filter = ['is_active', 'date_start']
    search_fields = ['number', 'recipient__last_name']
    inlines = [ContractServiceInline]
    date_hierarchy = 'date_start'


@admin.register(ContractService)
class ContractServiceAdmin(admin.ModelAdmin):
    list_display = ['contract', 'service', 'service_limit_display']
    list_filter = ['contract__recipient__department']
    search_fields = ['contract__number', 'service__name']
    autocomplete_fields = ['contract', 'service']
    
    def service_limit_display(self, obj):
        if obj.service.max_quantity_per_month:
            return f"макс. {obj.service.max_quantity_per_month}/мес"
        return "без ограничений"
    service_limit_display.short_description = 'Ограничение услуги'


@admin.register(RecipientHistory)
class RecipientHistoryAdmin(admin.ModelAdmin):
    """Админка для единой истории изменений"""
    list_display = ['recipient', 'date', 'placement_change_display', 'department_change_display',
                    'room_change_display', 'reason', 'changed_by']
    list_filter = ['date', 'new_placement', 'new_department']
    search_fields = ['recipient__last_name', 'recipient__first_name', 'reason']
    date_hierarchy = 'date'
    readonly_fields = ['recipient', 'old_placement', 'new_placement', 'old_department', 'new_department',
                       'old_room', 'new_room', 'old_status', 'new_status', 'reason', 'date', 'changed_by', 'created_at']
    
    def placement_change_display(self, obj):
        """Отображение изменения размещения"""
        if obj.old_placement and obj.new_placement:
            old = obj.get_placement_display_value(obj.old_placement)
            new = obj.get_placement_display_value(obj.new_placement)
            if obj.old_placement != obj.new_placement:
                return format_html('<span style="color: #666;">{}</span> → <strong>{}</strong>', old, new)
            return new
        elif obj.new_placement:
            return obj.get_placement_display_value(obj.new_placement)
        return '—'
    placement_change_display.short_description = 'Размещение'
    
    def department_change_display(self, obj):
        """Отображение изменения отделения"""
        if obj.old_department and obj.new_department:
            if obj.old_department != obj.new_department:
                return format_html('<span style="color: #666;">{}</span> → <strong>{}</strong>',
                                   obj.old_department.name, obj.new_department.name)
            return obj.new_department.name
        elif obj.new_department:
            return obj.new_department.name
        return '—'
    department_change_display.short_description = 'Отделение'
    
    def room_change_display(self, obj):
        """Отображение изменения комнаты"""
        if obj.old_room and obj.new_room:
            if obj.old_room != obj.new_room:
                return format_html('<span style="color: #666;">{}</span> → <strong>{}</strong>',
                                   obj.old_room, obj.new_room)
            return obj.new_room
        elif obj.new_room:
            return obj.new_room
        return '—'
    room_change_display.short_description = 'Комната'


@admin.register(MonthlyRecipientData)
class MonthlyRecipientDataAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'year', 'month', 'income', 'pension_payment', 'created_at']
    list_filter = ['year', 'month', 'recipient__department']
    search_fields = ['recipient__last_name', 'recipient__first_name', 'recipient__patronymic']
    date_hierarchy = 'created_at'
    autocomplete_fields = ['recipient']
    ordering = ['-year', '-month', 'recipient__last_name']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('recipient', 'year', 'month')
        }),
        ('Финансовые данные', {
            'fields': ('income', 'pension_payment'),
        }),
    )
