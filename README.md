# Система учета социальных услуг

Django 5.x проект для автоматизации учета социальных услуг в учреждении на 500 проживающих.

## Технологии

- **Backend**: Django 5.x
- **Database**: SQLite (разработка) / PostgreSQL (продакшен)
- **Frontend**: Tailwind CSS, HTMX
- **PDF Generation**: WeasyPrint
- **Static Files**: Whitenoise

## Функционал

### Модели данных

1. **Recipient (ПСУ)** - Получатель социальных услуг
   - ФИО, отделение, статус (проживает/отпуск/выбыл), дата рождения, фото
   
2. **Service (Услуга)** - Социальная услуга
   - Название, код, цена, категория
   - Поддержка иерархии (подуслуги)
   
3. **Contract (ИППСУ)** - Индивидуальный план предоставления услуг
   - Фильтрует список доступных услуг для конкретного ПСУ
   
4. **ServiceLog** - Запись в табеле
   - Связь с Recipient, Service и User
   - Дата оказания, количество
   - Цена копируется в момент записи (история цен)

### Роли пользователей

- **Администратор** - полный доступ ко всему
- **Отдел кадров** - видит всех, редактирует справочники
- **Медик/Специалист** - видит только своё отделение, вносит услуги

### Интерфейс табеля

- Grid View с днями месяца
- Auto-save через HTMX (без кнопки "Сохранить")
- Цветовая индикация количества услуг
- Закреплённые колонки с названиями услуг

### Генерация актов

- Сбор данных за выбранный месяц
- Группировка услуг, подсчёт итогов
- Экспорт в PDF (WeasyPrint)

---

## Установка

### Вариант 1: Локальная разработка

#### 1. Клонирование и виртуальное окружение

```bash
cd social_services
python -m venv venv

# Linux/Mac
source venv/bin/activate

# Windows
venv\Scripts\activate
```

#### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

#### 3. Миграции базы данных

```bash
python manage.py migrate
```

#### 4. Загрузка тестовых данных (опционально)

```bash
python manage.py setup_demo
```

Это создаст:
- Пользователей (admin, hr, medic1-4, mercy)
- 5 отделений
- 38 социальных услуг
- 500 проживающих с ИППСУ

#### 5. Запуск сервера

```bash
python manage.py runserver
```

Откройте http://127.0.0.1:8000/

---

### Вариант 2: Docker

#### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd social_services
```

#### 2. Создание .env файла

```bash
cp .env.example .env
# Отредактируйте .env, установите SECRET_KEY и ALLOWED_HOSTS
```

#### 3. Создание директорий для данных

```bash
mkdir -p media data
```

#### 4. Запуск контейнера

```bash
docker-compose up -d --build
```

Приложение будет доступно на http://localhost:8000/

#### 5. Создание суперпользователя

```bash
docker-compose exec web python manage.py createsuperuser
```

#### 6. Загрузка тестовых данных (опционально)

```bash
docker-compose exec web python manage.py setup_demo
```

---

## Тестовые аккаунты

| Логин | Пароль | Роль |
|-------|--------|------|
| admin | admin | Администратор |
| hr | hr123 | Отдел кадров |
| medic1 | medic1123 | Медик (Отделение 1) |
| medic2 | medic2123 | Медик (Отделение 2) |
| medic3 | medic3123 | Медик (Отделение 3) |
| medic4 | medic4123 | Медик (Отделение 4) |
| mercy | mercy123 | Медик (Милосердие) |

---

## Структура проекта

```
social_services/
├── apps/
│   ├── core/           # Ядро системы (User, Department)
│   ├── services/       # Услуги и табель
│   ├── recipients/     # Проживающие и ИППСУ
│   └── reports/        # Генерация актов
├── config/             # Настройки Django
├── templates/          # Шаблоны
│   ├── base.html
│   ├── core/
│   ├── services/
│   ├── recipients/
│   └── reports/
├── static/             # Статические файлы
├── media/              # Загруженные файлы (фото)
├── manage.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## API endpoints

- `POST /services/api/service-log/` - Сохранение записи табеля
- `GET /recipients/api/by-department/<id>/` - Список проживающих по отделению

## Использование HTMX

Табель использует HTMX для auto-save. При клике на ячейку:

1. Отправляется POST запрос на `/services/api/service-log/`
2. Данные сохраняются в БД
3. Возвращается обновлённое значение и итог

Пример запроса:
```json
{
    "recipient_id": 1,
    "service_id": 5,
    "day": 15,
    "month": 1,
    "year": 2024,
    "quantity": 2
}
```

---

## Перенос на другой сервер

### Шаг 1: Экспорт данных

На исходном сервере:

```bash
# Экспорт базы данных (SQLite)
cp db.sqlite3 db_backup.sqlite3

# Или для PostgreSQL
pg_dump social_services > backup.sql

# Архивация медиа-файлов
tar -czvf media_backup.tar.gz media/
```

### Шаг 2: Перенос файлов

```bash
# Клонирование репозитория на новом сервере
git clone <repository-url>
cd social_services

# Копирование данных
cp db_backup.sqlite3 db.sqlite3
tar -xzvf media_backup.tar.gz
```

### Шаг 3: Запуск

```bash
# Создание .env
cp .env.example .env
# Отредактируйте .env

# Запуск Docker
docker-compose up -d --build
```

---

## Устранение неполадок

### Админка без стилей (белый текст на белом фоне)

**Причина**: В продакшене Django не раздаёт статические файлы.

**Решение**: Проект использует Whitenoise для раздачи статики. Убедитесь, что:
1. `whitenoise` установлен в requirements.txt
2. `whitenoise.middleware.WhiteNoiseMiddleware` добавлен в MIDDLEWARE
3. `STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'`

### Фото не отображаются

**Причина**: Медиа-файлы не раздаются в продакшене.

**Решение**: 
1. Убедитесь, что папка `media/` примонтирована в docker-compose.yml
2. Проверьте права доступа к папке media
3. Файлы должны быть в `media/recipients/photos/{id}/файл.jpg`

### Ошибки WeasyPrint

**Причина**: Отсутствуют системные библиотеки для рендеринга PDF.

**Решение**: Dockerfile уже включает необходимые зависимости. При локальной установке:

```bash
# Ubuntu/Debian
sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0

# macOS
brew install pango gdk-pixbuf
```

---

## Лицензия

MIT
