from django.contrib import admin
from .models import Product, MonthlyRequest, RequestItem, DigitalProfile


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'unit', 'price', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']
    list_editable = ['price', 'is_active']


class RequestItemInline(admin.TabularInline):
    model = RequestItem
    extra = 1
    fields = ['product', 'quantity', 'price']
    
    def get_readonly_fields(self, request, obj=None):
        if obj and obj.pk:
            return ['price']
        return []


@admin.register(MonthlyRequest)
class MonthlyRequestAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'year', 'month', 'status', 'total_amount', 'created_at']
    list_filter = ['status', 'year', 'month']
    search_fields = ['recipient__last_name', 'recipient__first_name']
    inlines = [RequestItemInline]
    readonly_fields = ['total_amount', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('recipient', 'year', 'month', 'status')
        }),
        ('Финансы', {
            'fields': ('total_amount', 'notes')
        }),
        ('Метаданные', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            instance.save()
        formset.save_m2m()
        form.instance.calculate_total()


@admin.register(DigitalProfile)
class DigitalProfileAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'unique_id', 'is_public', 'created_at']
    list_filter = ['is_public']
    search_fields = ['recipient__last_name', 'recipient__first_name', 'unique_id']
    readonly_fields = ['unique_id', 'qr_code', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('recipient', 'unique_id', 'qr_code', 'is_public')
        }),
        ('Персональная информация', {
            'fields': ('bio', 'hobbies', 'favorite_activities')
        }),
        ('Здоровье и питание', {
            'fields': ('special_needs', 'dietary_restrictions', 'medical_notes')
        }),
        ('Экстренные контакты', {
            'fields': ('emergency_contact', 'emergency_phone')
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )