from django.urls import path
from . import views

app_name = 'recipients'

urlpatterns = [
    path('', views.recipient_list, name='list'),
    path('<int:pk>/', views.recipient_detail, name='detail'),
    path('api/by-department/<int:department_id>/', views.recipients_by_department, name='by_department'),
]
