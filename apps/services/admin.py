from django.contrib import admin
from .models import ServiceCategory, Service, ServiceLog


class ServiceInline(admin.TabularInline):
    model = Service
    extra = 0
    fields = ['code', 'name', 'price', 'is_active']


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
    list_display = ['code', 'name', 'category', 'parent', 'price', 'is_active']
    list_filter = ['category', 'is_active', 'parent']
    search_fields = ['code', 'name']
    list_editable = ['price', 'is_active']


@admin.register(ServiceLog)
class ServiceLogAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'service', 'date', 'quantity', 'price_at_service', 'provider']
    list_filter = ['date', 'service__category', 'recipient__department']
    search_fields = ['recipient__last_name', 'service__name']
    date_hierarchy = 'date'
    readonly_fields = ['price_at_service', 'created_at', 'updated_at']
