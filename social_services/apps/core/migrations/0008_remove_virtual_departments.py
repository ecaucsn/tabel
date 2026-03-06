# -*- coding: utf-8 -*-
from django.db import migrations


def remove_virtual_departments(apps, schema_editor):
    """Удаляет виртуальные отделения (больница, отпуск, умер)"""
    Department = apps.get_model('core', 'Department')
    
    # Удаляем отделения с типами hospital, vacation, deceased
    Department.objects.filter(
        department_type__in=['hospital', 'vacation', 'deceased']
    ).delete()


def reverse_remove(apps, schema_editor):
    """Ничего не делаем при откате"""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0007_location_type_data'),
        ('recipients', '0015_migrate_placement_to_location_type'),
    ]
    
    operations = [
        migrations.RunPython(remove_virtual_departments, reverse_remove),
    ]
