# -*- coding: utf-8 -*-
from django.db import migrations


def migrate_placement_to_location_type(apps, schema_editor):
    """Переносит данные из placement в location_type"""
    Recipient = apps.get_model('recipients', 'Recipient')
    LocationType = apps.get_model('core', 'LocationType')
    
    # Маппинг placement -> location_type code
    placement_map = {
        'internat': 'internat',
        'hospital': 'hospital',
        'vacation': 'vacation',
        'discharged': 'deceased',
    }
    
    # Получаем все типы местоположения
    location_types = {lt.code: lt for lt in LocationType.objects.all()}
    
    # Обновляем всех получателей
    for recipient in Recipient.objects.all():
        placement = recipient.placement or 'internat'
        location_code = placement_map.get(placement, 'internat')
        if location_code in location_types:
            recipient.location_type = location_types[location_code]
            recipient.save(update_fields=['location_type'])


def reverse_migrate(apps, schema_editor):
    """Откат - очищает location_type"""
    Recipient = apps.get_model('recipients', 'Recipient')
    Recipient.objects.update(location_type=None)


class Migration(migrations.Migration):
    dependencies = [
        ('recipients', '0014_add_location_type_to_recipient'),
        ('core', '0007_location_type_data'),
    ]
    
    operations = [
        migrations.RunPython(migrate_placement_to_location_type, reverse_migrate),
    ]
