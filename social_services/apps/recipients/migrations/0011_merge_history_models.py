# -*- coding: utf-8 -*-
"""
Миграция: объединение StatusHistory и PlacementHistory в единую модель RecipientHistory

Эта миграция:
1. Создаёт новую модель RecipientHistory
2. Переносит данные из StatusHistory и PlacementHistory
3. Удаляет старые модели
"""

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


def merge_history_data(apps, schema_editor):
    """Перенос данных из старых моделей в новую"""
    RecipientHistory = apps.get_model('recipients', 'RecipientHistory')
    StatusHistory = apps.get_model('recipients', 'StatusHistory')
    PlacementHistory = apps.get_model('recipients', 'PlacementHistory')
    
    # Переносим данные из PlacementHistory (более полная модель)
    for ph in PlacementHistory.objects.all():
        RecipientHistory.objects.create(
            recipient_id=ph.recipient_id,
            old_department_id=ph.old_department_id,
            new_department_id=ph.new_department_id,
            old_room=ph.old_room,
            new_room=ph.new_room,
            old_status=ph.old_status,
            new_status=ph.new_status,
            reason=ph.reason,
            date=ph.date,
            changed_by_id=ph.changed_by_id,
            created_at=ph.created_at,
        )
    
    # Переносим уникальные записи из StatusHistory (которых нет в PlacementHistory)
    for sh in StatusHistory.objects.all():
        # Проверяем, есть ли уже такая запись в PlacementHistory
        existing = PlacementHistory.objects.filter(
            recipient_id=sh.recipient_id,
            new_department_id=sh.new_department_id,
            created_at__date=sh.created_at.date()
        ).exists()
        
        if not existing:
            RecipientHistory.objects.create(
                recipient_id=sh.recipient_id,
                old_department_id=sh.old_department_id,
                new_department_id=sh.new_department_id,
                old_room='',
                new_room='',
                old_status=sh.old_status,
                new_status=sh.new_status,
                reason=sh.reason,
                date=sh.created_at.date(),
                changed_by_id=sh.changed_by_id,
                created_at=sh.created_at,
            )


def reverse_merge(apps, schema_editor):
    """Обратная миграция - восстановление данных"""
    # При откате просто очищаем новую таблицу
    RecipientHistory = apps.get_model('recipients', 'RecipientHistory')
    RecipientHistory.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('recipients', '0010_add_monthly_recipient_data'),
    ]

    operations = [
        # Создаём новую модель RecipientHistory
        migrations.CreateModel(
            name='RecipientHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('old_room', models.CharField(blank=True, max_length=20, null=True, verbose_name='Предыдущая комната')),
                ('new_room', models.CharField(blank=True, max_length=20, null=True, verbose_name='Новая комната')),
                ('old_status', models.CharField(blank=True, choices=[('active', 'Проживает'), ('vacation', 'Отпуск'), ('hospital', 'Больница'), ('discharged', 'Выбыл')], max_length=20, null=True, verbose_name='Предыдущий статус')),
                ('new_status', models.CharField(blank=True, choices=[('active', 'Проживает'), ('vacation', 'Отпуск'), ('hospital', 'Больница'), ('discharged', 'Выбыл')], max_length=20, null=True, verbose_name='Новый статус')),
                ('reason', models.TextField(blank=True, verbose_name='Причина/Комментарий')),
                ('date', models.DateField(verbose_name='Дата изменения')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Кто изменил')),
                ('new_department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='history_arrivals', to='core.department', verbose_name='Новое отделение')),
                ('old_department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='history_departures', to='core.department', verbose_name='Предыдущее отделение')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history', to='recipients.recipient', verbose_name='Получатель услуг')),
            ],
            options={
                'verbose_name': 'История изменений',
                'verbose_name_plural': 'История изменений',
                'ordering': ['-date', '-created_at'],
            },
        ),
        
        # Переносим данные
        migrations.RunPython(merge_history_data, reverse_merge),
        
        # Удаляем старые модели
        migrations.DeleteModel(
            name='StatusHistory',
        ),
        migrations.DeleteModel(
            name='PlacementHistory',
        ),
    ]
