from django.urls import path
from . import views

app_name = 'modules'

urlpatterns = [
    # Заявки на паёк
    path('requests/', views.RequestsListView.as_view(), name='requests'),
    path('requests/create/', views.RequestCreateView.as_view(), name='request_create'),
    path('requests/<int:pk>/', views.RequestDetailView.as_view(), name='request_detail'),
    path('requests/<int:pk>/edit/', views.RequestUpdateView.as_view(), name='request_edit'),
    path('requests/<int:pk>/delete/', views.RequestDeleteView.as_view(), name='request_delete'),
    path('requests/<int:request_id>/add-item/', views.add_request_item, name='add_request_item'),
    path('requests/<int:request_id>/remove-item/<int:item_id>/', views.remove_request_item, name='remove_request_item'),
    path('requests/<int:pk>/submit/', views.submit_request, name='submit_request'),
    
    # Массовое создание заявок на продукты
    path('monthly-purchase/', views.monthly_purchase_create, name='monthly_purchase_create'),
    path('monthly-purchase/save/', views.monthly_purchase_save, name='monthly_purchase_save'),
    
    # Цифровой профиль
    path('digital-profile/', views.DigitalProfileListView.as_view(), name='digital_profile'),
    path('digital-profile/create/', views.DigitalProfileCreateView.as_view(), name='digital_profile_create'),
    path('digital-profile/<int:pk>/', views.DigitalProfileDetailView.as_view(), name='digital_profile_detail'),
    path('digital-profile/<int:pk>/edit/', views.DigitalProfileUpdateView.as_view(), name='digital_profile_edit'),
    path('digital-profile/<int:pk>/qr/', views.generate_qr, name='generate_qr'),
    
    # Публичный доступ к профилю
    path('public/<uuid:profile_id>/', views.public_profile, name='public_profile'),
    
    # Пенсии
    path('pensions/', views.PensionListView.as_view(), name='pensions'),
    path('pensions/create/', views.PensionAccountCreateView.as_view(), name='pension_create'),
    path('pensions/<int:pk>/', views.PensionDetailView.as_view(), name='pension_detail'),
    path('pensions/<int:pk>/edit/', views.PensionAccountUpdateView.as_view(), name='pension_edit'),
    path('pensions/<int:account_id>/add-accrual/', views.add_pension_accrual, name='add_pension_accrual'),
    path('pensions/<int:account_id>/add-expense/', views.add_pension_expense, name='add_pension_expense'),
    path('pensions/accrual/create/', views.PensionAccrualCreateView.as_view(), name='pension_accrual_create'),
    path('pensions/expense/create/', views.PensionExpenseCreateView.as_view(), name='pension_expense_create'),
    path('pensions/savings/create/', views.PensionSavingsCreateView.as_view(), name='pension_savings_create'),
]