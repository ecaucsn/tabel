from django.urls import path
from . import views

app_name = 'services'

urlpatterns = [
    path('tabel/', views.tabel_view, name='tabel'),
    path('tabel/print/', views.tabel_print_view, name='tabel_print'),
    path('api/service-log/', views.service_log_api, name='service_log_api'),
    path('api/service-log/<int:recipient_id>/<int:service_id>/<str:date>/', views.get_service_log, name='get_service_log'),
    path('api/clear-month/', views.clear_month_api, name='clear_month_api'),
    path('api/clear-day/', views.clear_day_api, name='clear_day_api'),
]
