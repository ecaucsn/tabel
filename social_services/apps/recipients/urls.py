from django.urls import path
from . import views

app_name = 'recipients'

urlpatterns = [
    path('', views.recipient_list, name='list'),
    path('<int:pk>/', views.recipient_detail, name='detail'),
    path('<int:pk>/contract/', views.edit_contract, name='contract'),
    path('<int:pk>/change-status/', views.change_status, name='change_status'),
    path('contracts/', views.contract_list, name='contract_list'),
    path('lists/', views.lists_page, name='lists'),
    path('lists/residents/', views.residents_list_page, name='residents_list'),
    path('lists/residents/print/', views.residents_list_print, name='residents_list_print'),
    path('lists/jubilees/', views.jubilees_list, name='jubilees'),
    path('api/by-department/<int:department_id>/', views.recipients_by_department, name='by_department'),
]
