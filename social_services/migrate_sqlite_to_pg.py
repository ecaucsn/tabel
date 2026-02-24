#!/usr/bin/env python
"""
Скрипт для переноса данных из SQLite в PostgreSQL.
Запуск: python migrate_sqlite_to_pg.py
"""

import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connections, transaction


def main():
    print("Начало переноса данных из SQLite в PostgreSQL")
    print("=" * 50)
    
    # Подключаемся к базам
    sqlite_conn = connections['sqlite']
    pg_conn = connections['default']
    
    sqlite_cursor = sqlite_conn.cursor()
    pg_cursor = pg_conn.cursor()
    
    # Отключаем проверку внешних ключей в PostgreSQL
    print("\nОтключение проверки внешних ключей...")
    
    # Получаем список всех таблиц
    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'django_migrations'")
    tables = [row[0] for row in sqlite_cursor.fetchall()]
    print(f"Найдено таблиц: {len(tables)}")
    
    # Отключаем триггеры внешних ключей в PostgreSQL
    pg_cursor.execute("SET session_replication_role = 'replica';")
    
    total = 0
    
    # Порядок переноса таблиц (сначала независимые)
    table_order = [
        'core_user',
        'core_department',
        'services_servicecategory',  # Категории услуг (должны быть до услуг)
        'recipients_recipient',
        'recipients_placementhistory',
        'recipients_contract',
        'recipients_contractservice',
        'recipients_monthlyrecipientdata',
        'services_servicefrequency',
        'services_service',
        'services_serviceschedule',
        'services_servicelog',
        'services_tabellock',
        'django_admin_log',
        'django_session',
    ]
    
    for table in table_order:
        if table in tables:
            count = migrate_table(sqlite_cursor, pg_cursor, table)
            total += count
    
    # Включаем проверку внешних ключей
    print("\nВключение проверки внешних ключей...")
    pg_cursor.execute("SET session_replication_role = 'origin';")
    
    # Сбрасываем последовательности
    print("\nСброс последовательностей...")
    for table in table_order:
        if table in tables:
            try:
                pg_cursor.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1))")
            except Exception as e:
                print(f"  Не удалось сбросить последовательность для {table}: {e}")
    
    # Завершаем транзакцию
    transaction.commit(using='default')
    
    # Закрываем соединения
    sqlite_cursor.close()
    pg_cursor.close()
    
    print("\n" + "=" * 50)
    print(f"Перенос завершён! Всего перенесено записей: {total}")


def migrate_table(sqlite_cursor, pg_cursor, table_name):
    """Переносит данные для одной таблицы"""
    print(f"\nПеренос таблицы: {table_name}")
    
    # Очищаем таблицу (без CASCADE, т.к. внешние ключи отключены)
    try:
        pg_cursor.execute(f"TRUNCATE TABLE {table_name}")
        print(f"  Таблица очищена")
    except Exception as e:
        print(f"  Не удалось очистить таблицу: {e}")
    
    # Получаем структуру таблицы из SQLite
    sqlite_cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = sqlite_cursor.fetchall()
    columns = [col[1] for col in columns_info]
    
    # Читаем данные из SQLite
    sqlite_cursor.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cursor.fetchall()
    
    if not rows:
        print(f"  Нет данных")
        return 0
    
    # Формируем INSERT запрос с экранированием имён колонок
    columns_str = ', '.join(f'"{col}"' for col in columns)
    placeholders = ', '.join(['%s'] * len(columns))
    sql = f'INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})'
    
    # Вставляем данные в PostgreSQL
    count = 0
    for row in rows:
        try:
            pg_cursor.execute(sql, row)
            count += 1
        except Exception as e:
            print(f"  Ошибка при вставке: {e}")
            continue
    
    print(f"  Перенесено записей: {count}")
    return count


if __name__ == '__main__':
    main()
