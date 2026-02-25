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
    
    # Цифровой профиль
    path('digital-profile/', views.DigitalProfileListView.as_view(), name='digital_profile'),
    path('digital-profile/create/', views.DigitalProfileCreateView.as_view(), name='digital_profile_create'),
    path('digital-profile/<int:pk>/', views.DigitalProfileDetailView.as_view(), name='digital_profile_detail'),
    path('digital-profile/<int:pk>/edit/', views.DigitalProfileUpdateView.as_view(), name='digital_profile_edit'),
    path('digital-profile/<int:pk>/qr/', views.generate_qr, name='generate_qr'),
    
    # Публичный доступ к профилю
    path('public/<uuid:profile_id>/', views.public_profile, name='public_profile'),
]