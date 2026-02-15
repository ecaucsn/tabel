from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('act/', views.act_generator, name='act_generator'),
    path('act/<int:recipient_id>/<int:year>/<int:month>/', views.generate_act, name='generate_act'),
    path('act/<int:recipient_id>/<int:year>/<int:month>/print/', views.print_act, name='print_act'),
]
