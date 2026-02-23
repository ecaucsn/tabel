#!/usr/bin/env python
"""
Скрипт для переноса данных из SQLite в PostgreSQL.
Запуск: python migrate_data.py
"""

import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connections
from django.apps import apps


def main():
    print("Начало переноса данных из SQLite в PostgreSQL")
    print("=" * 50)
    
    # Подключаемся к SQLite через настроенное соединение
    sqlite_conn = connections['sqlite']
    sqlite_cursor = sqlite_conn.cursor()
    
    # Подключаемся к PostgreSQL
    pg_conn = connections['default']
    pg_cursor = pg_conn.cursor()
    
    # Очищаем таблицы PostgreSQL (в обратном порядке зависимостей)
    print("\nОчистка таблиц PostgreSQL...")
    models_to_clear = [
        'ServiceLog',
        'TabelLock', 
        'ServiceSchedule',
        'ServiceFrequency',
        'ContractService',
        'Contract',
        'MonthlyRecipientData',
        'PlacementHistory',
        'Recipient',
        'Department',
        'User',
    ]
    
    for model_name in models_to_clear:
        try:
            model = apps.get_model(model_name)
            pg_cursor.execute(f"TRUNCATE TABLE {model._meta.db_table} CASCADE")
            print(f"  Очищена таблица: {model._meta.db_table}")
        except Exception as e:
            print(f"  Не удалось очистить {model_name}: {e}")
    
    # Переносим данные (в порядке зависимостей)
    print("\nПеренос данных...")
    models_order = [
        'core.User',
        'core.Department',
        'recipients.Recipient',
        'recipients.PlacementHistory',
        'recipients.Contract',
        'recipients.ContractService',
        'recipients.MonthlyRecipientData',
        'services.ServiceFrequency',
        'services.Service',
        'services.ServiceSchedule',
        'services.ServiceLog',
        'services.TabelLock',
    ]
    
    total = 0
    for model_path in models_order:
        try:
            model = apps.get_model(model_path)
            count = migrate_model_data(model, sqlite_cursor, pg_cursor)
            total += count
        except Exception as e:
            print(f"Ошибка при переносе {model_path}: {e}")
    
    # Сбрасываем последовательности
    print("\nСброс последовательностей...")
    pg_cursor.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name LIKE '%'
    """)
    for (table_name,) in pg_cursor.fetchall():
        try:
            pg_cursor.execute(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE(MAX(id), 1)) FROM {table_name}")
        except:
            pass
    
    # Закрываем соединения
    sqlite_cursor.close()
    pg_cursor.close()
    
    print("\n" + "=" * 50)
    print(f"Перенос завершён! Всего перенесено записей: {total}")


def migrate_model_data(model, sqlite_cursor, pg_cursor):
    """Переносит данные для одной модели"""
    table_name = model._meta.db_table
    print(f"Перенос таблицы: {table_name}")
    
    # Получаем список полей
    fields = [f for f in model._meta.fields if not f.auto_created]
    field_names = [f.column for f in fields]
    
    # Читаем данные из SQLite
    sqlite_cursor.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cursor.fetchall()
    
    if not rows:
        print(f"  Нет данных в таблице {table_name}")
        return 0
    
    # Формируем INSERT запрос
    columns_str = ', '.join(field_names)
    placeholders = ', '.join(['%s'] * len(field_names))
    sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
    
    # Вставляем данные в PostgreSQL
    count = 0
    for row in rows:
        try:
            # Создаём словарь значений
            row_dict = {}
            for i, col in enumerate(sqlite_cursor.description):
                row_dict[col[0]] = row[i]
            
            # Формируем значения в правильном порядке
            values = []
            for f in fields:
                val = row_dict.get(f.column)
                # Обработка None для ForeignKey
                if val is None and f.null:
                    values.append(None)
                elif val is None and f.has_default():
                    values.append(f.get_default())
                else:
                    values.append(val)
            
            pg_cursor.execute(sql, values)
            count += 1
        except Exception as e:
            print(f"  Ошибка при вставке: {e}")
            continue
    
    print(f"  Перенесено записей: {count}")
    return count


if __name__ == '__main__':
    main()
