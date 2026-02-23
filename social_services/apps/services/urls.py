from django.urls import path
from . import views

app_name = 'services'

urlpatterns = [
    path('tabel/', views.tabel_view, name='tabel'),
    path('tabel/print/', views.tabel_print_view, name='tabel_print'),
    path('list/', views.services_list_view, name='list'),
    path('api/service-log/', views.service_log_api, name='service_log_api'),
    path('api/service-log/<int:recipient_id>/<int:service_id>/<str:date>/', views.get_service_log, name='get_service_log'),
    path('api/clear-month/', views.clear_month_api, name='clear_month_api'),
    path('api/clear-day/', views.clear_day_api, name='clear_day_api'),
    path('api/autofill/', views.autofill_tabel, name='autofill_tabel'),
    path('api/service-logs/', views.get_service_logs_api, name='get_service_logs_api'),
    path('api/toggle-lock/', views.toggle_lock_api, name='toggle_lock_api'),
]
