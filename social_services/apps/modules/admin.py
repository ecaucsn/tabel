from django.contrib import admin
from .models import (
    Product, MonthlyRequest, RequestItem, DigitalProfile,
    PensionAccount, PensionAccrual, PensionExpense, PensionSavings
)


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


# ==================== Pension Admin ====================

class PensionAccrualInline(admin.TabularInline):
    model = PensionAccrual
    extra = 0
    fields = ['year', 'month', 'amount', 'source', 'accrued_date']
    readonly_fields = ['created_at']


class PensionExpenseInline(admin.TabularInline):
    model = PensionExpense
    extra = 0
    fields = ['year', 'month', 'amount', 'category', 'description']
    readonly_fields = ['created_at']


@admin.register(PensionAccount)
class PensionAccountAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'pension_type', 'pension_number', 'monthly_pension_amount', 'balance', 'created_at']
    list_filter = ['pension_type']
    search_fields = ['recipient__last_name', 'recipient__first_name', 'pension_number']
    readonly_fields = ['balance', 'created_at', 'updated_at']
    inlines = [PensionAccrualInline, PensionExpenseInline]
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('recipient', 'pension_type', 'pension_number')
        }),
        ('Финансы', {
            'fields': ('monthly_pension_amount', 'balance', 'notes')
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PensionAccrual)
class PensionAccrualAdmin(admin.ModelAdmin):
    list_display = ['account', 'year', 'month', 'amount', 'source', 'accrued_date', 'created_at']
    list_filter = ['year', 'month', 'source']
    search_fields = ['account__recipient__last_name', 'account__recipient__first_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('account', 'year', 'month', 'amount')
        }),
        ('Дополнительно', {
            'fields': ('accrued_date', 'source', 'notes')
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PensionExpense)
class PensionExpenseAdmin(admin.ModelAdmin):
    list_display = ['account', 'year', 'month', 'amount', 'category', 'description', 'created_at']
    list_filter = ['year', 'month', 'category']
    search_fields = ['account__recipient__last_name', 'account__recipient__first_name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('account', 'year', 'month', 'amount', 'category')
        }),
        ('Дополнительно', {
            'fields': ('description', 'expense_date', 'related_request')
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


@admin.register(PensionSavings)
class PensionSavingsAdmin(admin.ModelAdmin):
    list_display = ['account', 'year', 'month', 'amount', 'purpose', 'created_at']
    list_filter = ['year', 'month']
    search_fields = ['account__recipient__last_name', 'account__recipient__first_name', 'purpose']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('account', 'year', 'month', 'amount', 'purpose')
        }),
        ('Метаданные', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )