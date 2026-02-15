from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Recipient, Contract, ContractService


class ContractServiceInline(admin.TabularInline):
    model = ContractService
    extra = 1
    autocomplete_fields = ['service']
    fields = ['service', 'max_quantity_per_month']


@admin.register(Recipient)
class RecipientAdmin(admin.ModelAdmin):
    list_display = ['photo_preview', 'full_name', 'birth_date', 'department', 'room', 'status', 'age']
    list_filter = ['status', 'department']
    search_fields = ['last_name', 'first_name', 'patronymic']
    list_editable = ['status', 'room']
    date_hierarchy = 'admission_date'
    
    fieldsets = (
        ('Персональные данные', {
            'fields': ('photo', 'photo_preview_admin', 'last_name', 'first_name', 'patronymic', 'birth_date')
        }),
        ('Размещение', {
            'fields': ('department', 'room', 'status', 'admission_date', 'discharge_date')
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


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['number', 'recipient', 'date_start', 'date_end', 'is_active']
    list_filter = ['is_active', 'date_start']
    search_fields = ['number', 'recipient__last_name']
    inlines = [ContractServiceInline]
    date_hierarchy = 'date_start'


@admin.register(ContractService)
class ContractServiceAdmin(admin.ModelAdmin):
    list_display = ['contract', 'service', 'max_quantity_per_month', 'limit_display']
    list_filter = ['contract__recipient__department']
    search_fields = ['contract__number', 'service__name']
    autocomplete_fields = ['contract', 'service']
    list_editable = ['max_quantity_per_month']
    
    def limit_display(self, obj):
        if obj.max_quantity_per_month:
            return f"макс. {obj.max_quantity_per_month}/мес"
        return "без ограничений"
    limit_display.short_description = 'Ограничение'
