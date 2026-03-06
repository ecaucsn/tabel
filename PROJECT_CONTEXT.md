# Контекст проекта: СоцУслуги — Система учёта социальных услуг

> **Файл-справка для быстрого погружения в проект. Прикладывать при создании новых задач.**

---

## 📋 Краткое описание

**СоцУслуги** — Django-приложение для автоматизации дома социального обслуживания (до 500 проживающих). 
Учёт получателей услуг (ПСУ), ведение табелей оказанных услуг, формирование актов для бухгалтерии.

---

## 🛠 Технологический стек

| Компонент | Технология |
|-----------|------------|
| Backend | Django 5.x |
| Database | PostgreSQL (прод) / SQLite (dev) |
| Frontend | Tailwind CSS, HTMX |
| PDF | WeasyPrint |
| Static | Whitenoise |

---

## 📁 Структура проекта

```
social_services/
├── apps/
│   ├── core/           # User, Department, middleware, dashboard
│   ├── recipients/     # Recipient, Contract, StatusHistory
│   ├── services/       # Service, ServiceLog (табель), TabelLock
│   ├── reports/        # Генерация актов (PDF)
│   └── modules/        # Пенсионные счета, профили, заявки
├── config/             # settings.py, urls.py, wsgi.py
├── templates/          # HTML-шаблоны (base.html + по модулям)
├── static/             # Статика
├── media/              # Загруженные файлы (фото ПСУ)
└── docs/               # Документация
```

---

## 🗃 Ключевые модели

### apps.core
- **Department** — отделения (residential, mercy, hospital, vacation, deceased)
- **User** — пользователи с ролями (admin, hr, specialist, medic)

### apps.recipients
- **Recipient** — получатель социальных услуг (ФИО, отделение, комната, фото, доходы)
- **Contract** — ИППСУ (индивидуальный план услуг)
- **ContractService** — услуги в договоре
- **RecipientHistory** — единая история изменений (статусы, перемещения, комнаты)
- **MonthlyRecipientData** — месячные данные по доходам

### apps.services
- **Service** — социальная услуга (код, название, цена, категория, периодичность)
- **ServiceCategory** — категория услуг
- **ServiceFrequency** — периодичность (ежедневно, 1/месяц и т.д.)
- **ServiceSchedule** — расписание услуги по дням недели для отделения
- **ServiceLog** — запись в табеле (кто, кому, какая услуга, когда, сколько)
- **TabelLock** — блокировка табеля на месяц

### apps.modules
- **PensionAccount** — пенсионный счёт
- **PensionAccrual** / **PensionExpense** — начисления и расходы
- **Profile** — анкета работника
- **Request** — заявка на услуги

---

## 👥 Роли пользователей

| Роль | Код | Права |
|------|-----|-------|
| Администратор | `admin` | Полный доступ |
| Отдел кадров | `hr` | Просмотр всех, редактирование справочников |
| Специалист | `specialist` | Только своё отделение |
| Медик | `medic` | Только своё отделение |

**Middleware**: `DepartmentAccessMiddleware` ограничивает доступ медиков/специалистов своим отделением.

---

## 🔗 Основные URL-маршруты

| Путь | Описание |
|------|----------|
| `/` | Dashboard |
| `/login/`, `/logout/` | Авторизация |
| `/recipients/` | Список ПСУ |
| `/recipients/<id>/` | Карточка ПСУ |
| `/recipients/<id>/contract/` | ИППСУ |
| `/services/` | Справочник услуг |
| `/services/tabel/` | Табель учёта |
| `/reports/act/` | Генератор актов |
| `/modules/pensions/` | Пенсионные счета |
| `/modules/profiles/` | Анкеты работников |

---

## 🔌 API endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/services/api/service-log/` | Сохранение записи табеля |
| POST | `/services/api/autofill/` | Автозаполнение табеля |
| POST | `/services/api/clear-month/` | Очистка месяца |
| POST | `/services/api/toggle-lock/` | Блокировка табеля |
| GET | `/recipients/api/by-department/<id>/` | ПСУ по отделению |

---

## 📝 Важные особенности

### Табель услуг
- Grid-интерфейс с днями месяца
- **Auto-save через HTMX** (без кнопки "Сохранить")
- Автозаполнение по расписанию отделения
- Блокировка табеля для защиты от изменений
- Контроль лимитов по периодичности услуг

### ИППСУ (договор)
- Определяет список доступных услуг для ПСУ
- В табеле показываются только услуги из ИППСУ

### Генерация актов
- Сбор данных за месяц
- Расчёт: 75% от дохода — лимит
- PDF через WeasyPrint

---

## 🚀 Запуск проекта

```bash
cd social_services
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py setup_demo  # тестовые данные
python manage.py runserver
```

### Docker
```bash
docker-compose up -d --build
```

---

## 📌 Тестовые аккаунты

| Логин | Пароль | Роль |
|-------|--------|------|
| admin | admin | Администратор |
| hr | hr123456 | Отдел кадров |
| medic1 | medic1123 | Медик (Отделение 1) |

---

## 📚 Документация

- [`README.md`](social_services/README.md) — установка и запуск
- [`DOCUMENTATION.md`](social_services/DOCUMENTATION.md) — полное описание
- [`docs/autofill_algorithm.md`](social_services/docs/autofill_algorithm.md) — алгоритм автозаполнения табеля

---

## ⚠️ Частые проблемы

1. **Админка без стилей** — проверить Whitenoise в MIDDLEWARE
2. **Фото не отображаются** — проверить права на `media/`
3. **Ошибки WeasyPrint** — установить системные библиотеки (pango, gdk-pixbuf)

---

*Файл создан для экономии контекста при работе с AI-ассистентами.*
