# -*- coding: utf-8 -*-
from django.db import migrations


def create_location_types(apps, schema_editor):
    """Создаёт начальные типы местоположения"""
    LocationType = apps.get_model('core', 'LocationType')
    
    location_types = [
        {'code': 'internat', 'name': 'Интернат', 'is_active_status': True, 'requires_department': True, 'order': 10},
        {'code': 'hospital', 'name': 'Больница', 'is_active_status': False, 'requires_department': False, 'order': 20},
        {'code': 'vacation', 'name': 'Отпуск', 'is_active_status': False, 'requires_department': False, 'order': 30},
        {'code': 'deceased', 'name': 'Выбыл', 'is_active_status': False, 'requires_department': False, 'order': 40},
    ]
    
    for lt in location_types:
        LocationType.objects.update_or_create(
            code=lt['code'],
            defaults=lt
        )


def reverse_location_types(apps, schema_editor):
    """Удаляет типы местоположения"""
    LocationType = apps.get_model('core', 'LocationType')
    LocationType.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0006_add_location_type'),
    ]
    
    operations = [
        migrations.RunPython(create_location_types, reverse_location_types),
    ]
