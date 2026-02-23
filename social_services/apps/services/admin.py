from django.contrib import admin
from .models import ServiceCategory, Service, ServiceLog, ServiceFrequency, ServiceSchedule


class ServiceInline(admin.TabularInline):
    model = Service
    extra = 0
    fields = ['code', 'name', 'price', 'frequency', 'is_active']


class ServiceScheduleInline(admin.TabularInline):
    model = ServiceSchedule
    extra = 0
    fields = ['department', 'day_of_week', 'quantity']


@admin.register(ServiceFrequency)
class ServiceFrequencyAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'period_type', 'times_per_period', 'times_per_month_display', 'is_approximate', 'order']
    list_editable = ['short_name', 'period_type', 'times_per_period', 'is_approximate', 'order']
    ordering = ['order']
    
    def times_per_month_display(self, obj):
        result = obj.get_times_per_month()
        if result is None:
            return 'без огр.'
        return result
    times_per_month_display.short_description = 'Раз/мес'


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'order', 'services_count']
    list_editable = ['order']
    inlines = [ServiceInline]
    
    def services_count(self, obj):
        return obj.services.count()
    services_count.short_description = 'Кол-во услуг'


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'price', 'frequency', 'max_quantity_per_month', 'is_active', 'category', 'parent']
    list_filter = ['category', 'is_active', 'parent', 'frequency']
    search_fields = ['code', 'name']
    list_editable = ['price', 'frequency', 'is_active']
    inlines = [ServiceScheduleInline]


@admin.register(ServiceLog)
class ServiceLogAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'service', 'date', 'quantity', 'price_at_service', 'provider']
    list_filter = ['date', 'service__category', 'recipient__department']
    search_fields = ['recipient__last_name', 'service__name']
    date_hierarchy = 'date'
    readonly_fields = ['price_at_service', 'created_at', 'updated_at']


@admin.register(ServiceSchedule)
class ServiceScheduleAdmin(admin.ModelAdmin):
    list_display = ['service', 'department', 'day_of_week', 'quantity']
    list_filter = ['department', 'day_of_week', 'service__category']
    search_fields = ['service__code', 'service__name']
    list_editable = ['quantity']
