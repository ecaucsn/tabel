# -*- coding: utf-8 -*-
from django.db import migrations


def add_frequency_data(apps, schema_editor):
    """Добавление начальных данных периодичности услуг"""
    ServiceFrequency = apps.get_model('services', 'ServiceFrequency')
    
    frequencies = [
        # Ежедневные — без лимита (оказывается каждый день по определению)
        {'name': 'ежедневно', 'short_name': 'ежедн.', 'period_type': 'day', 'times_per_period': None, 'is_approximate': False, 'order': 10},
        
        # В месяц
        {'name': '1 в месяц', 'short_name': '1/мес', 'period_type': 'month', 'times_per_period': 1, 'is_approximate': False, 'order': 20},
        {'name': '2 в месяц', 'short_name': '2/мес', 'period_type': 'month', 'times_per_period': 2, 'is_approximate': False, 'order': 21},
        {'name': '4 в месяц', 'short_name': '4/мес', 'period_type': 'month', 'times_per_period': 4, 'is_approximate': False, 'order': 22},
        {'name': '8 в месяц', 'short_name': '8/мес', 'period_type': 'month', 'times_per_period': 8, 'is_approximate': False, 'order': 23},
        {'name': '12 в месяц', 'short_name': '12/мес', 'period_type': 'month', 'times_per_period': 12, 'is_approximate': False, 'order': 24},
        
        # В неделю (пересчёт в месяц = N * 4)
        {'name': '1 раз в неделю', 'short_name': '1/нед', 'period_type': 'week', 'times_per_period': 1, 'is_approximate': False, 'order': 30},
        {'name': '2 раза в неделю', 'short_name': '2/нед', 'period_type': 'week', 'times_per_period': 2, 'is_approximate': False, 'order': 31},
        {'name': '4 раза в неделю', 'short_name': '4/нед', 'period_type': 'week', 'times_per_period': 4, 'is_approximate': False, 'order': 32},
        
        # Приблизительные (до N)
        {'name': 'до 2 раз в неделю', 'short_name': 'до 2/нед', 'period_type': 'week', 'times_per_period': 2, 'is_approximate': True, 'order': 40},
        {'name': 'до 4 в день', 'short_name': 'до 4/день', 'period_type': 'day', 'times_per_period': 4, 'is_approximate': True, 'order': 41},
        
        # В год (пересчёт в месяц)
        {'name': '1 в год', 'short_name': '1/год', 'period_type': 'year', 'times_per_period': 1, 'is_approximate': False, 'order': 50},
        {'name': '2 в год', 'short_name': '2/год', 'period_type': 'year', 'times_per_period': 2, 'is_approximate': False, 'order': 51},
        
        # Без ограничений
        {'name': 'по необходимости', 'short_name': 'по необх.', 'period_type': 'month', 'times_per_period': None, 'is_approximate': False, 'order': 60},
    ]
    
    for freq_data in frequencies:
        ServiceFrequency.objects.create(**freq_data)


def remove_frequency_data(apps, schema_editor):
    """Удаление данных периодичности"""
    ServiceFrequency = apps.get_model('services', 'ServiceFrequency')
    ServiceFrequency.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('services', '0002_servicefrequency_service_max_quantity_per_month_and_more'),
    ]

    operations = [
        migrations.RunPython(add_frequency_data, remove_frequency_data),
    ]
