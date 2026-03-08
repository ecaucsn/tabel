# Хронология событий проживающих

## Описание реализации системы отслеживания изменений

---

## Содержание

1. [Общая информация](#1-общая-информация)
2. [Типы размещения](#2-типы-размещения)
3. [Модель истории](#3-модель-истории)
4. [Типы событий](#4-типы-событий)
5. [Сценарии использования](#5-сценарии-использования)
6. [API и методы](#6-api-и-методы)
7. [Интерфейс пользователя](#7-интерфейс-пользователя)

---

## 1. Общая информация

### 1.1 Назначение

Система хронологии событий предназначена для отслеживания всех изменений, происходящих с проживающими в доме-интернате:

- **Заселение** — первичное размещение проживающего в интернате
- **Перемещение** — перевод между отделениями и комнатами
- **Временное выбытие** — отпуск или госпитализация
- **Выбытие** — окончательный выезд (смерть, перевод в другое учреждение)

### 1.2 Принципы работы

1. **Единая таблица истории** — все события записываются в таблицу `RecipientHistory`
2. **Хронологический порядок** — записи сортируются по дате (от новых к старым)
3. **Актуальность на дату** — система определяет текущее состояние на основе самой поздней записи с датой ≤ сегодня
4. **Атомарность** — изменения сохраняются в транзакции вместе с записью истории

---

## 2. Типы размещения

### 2.1 Коды размещения

| Код | Название | Описание |
|-----|----------|----------|
| `internat` | Интернат | Проживающий находится в интернате |
| `vacation` | Отпуск | Временное выбытие в отпуск |
| `hospital` | Больница | Временное выбытие на лечение |
| `discharged` | Выбыл | Окончательное выбытие |

### 2.2 Связь с отделениями

```
┌─────────────────────────────────────────────────────────────┐
│                    Тип размещения                           │
├─────────────────────────────────────────────────────────────┤
│  internat    │  Отделение + Комната (обязательно)          │
│  vacation    │  Без отделения (виртуальное состояние)       │
│  hospital    │  Без отделения (виртуальное состояние)       │
│  discharged  │  Без отделения (архивное состояние)          │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Модель истории

### 3.1 Структура таблицы RecipientHistory

| Поле | Тип | Описание |
|------|-----|----------|
| `recipient` | ForeignKey | Ссылка на проживающего |
| `old_placement` | CharField | Предыдущее размещение |
| `new_placement` | CharField | Новое размещение |
| `old_department` | ForeignKey | Предыдущее отделение |
| `new_department` | ForeignKey | Новое отделение |
| `old_room` | CharField | Предыдущая комната |
| `new_room` | CharField | Новая комната |
| `reason` | TextField | Причина/комментарий |
| `date` | DateField | **Дата изменения** |
| `changed_by` | ForeignKey | Кто внёс изменения |
| `created_at` | DateTimeField | Время создания записи |

### 3.2 Индексы и сортировка

```python
class Meta:
    ordering = ['-date', '-created_at']  # От новых к старым
```

---

## 4. Типы событий

### 4.1 Классификация событий

Система автоматически определяет тип события на основе изменённых полей:

| Тип | Код | Условие определения |
|-----|-----|---------------------|
| **Заселение** | `admission` | `old_placement` был `null` или `discharged`, `new_placement` = `internat` |
| **Выбытие** | `discharge` | `new_placement` = `discharged` |
| **Изменение размещения** | `placement_change` | Изменился `placement` (кроме заселения/выбытия) |
| **Перевод** | `transfer` | Изменился `department` при том же `placement` |
| **Смена комнаты** | `room_change` | Изменился `room` при том же `department` |

### 4.2 Логика определения типа

```python
@property
def change_type(self):
    # Приоритет: размещение -> отделение -> комната
    if self.old_placement != self.new_placement and self.old_placement is not None:
        if self.new_placement == 'discharged':
            return 'discharge'
        elif self.old_placement == 'discharged' or self.old_placement is None:
            return 'admission'
        return 'placement_change'
    
    if self.old_department != self.new_department and self.old_department is not None:
        if self.new_department is None:
            return 'discharge'
        return 'transfer'
    
    if self.old_room != self.new_room and self.old_room is not None:
        return 'room_change'
    
    return 'placement_change'
```

---

## 5. Сценарии использования

### 5.1 Заселение нового проживающего

```
┌──────────────────────────────────────────────────────────────┐
│  СОБЫТИЕ: Заселение                                          │
├──────────────────────────────────────────────────────────────┤
│  До:    Нет данных (new_recipient)                           │
│  После: placement=internat, department=Отделение_1, room=101 │
│  Дата:  15.01.2026                                           │
│  Примечание: Первичное заселение                             │
└──────────────────────────────────────────────────────────────┘
```

**Запись в истории:**
```python
RecipientHistory.objects.create(
    recipient=recipient,
    old_placement=None,           # Не было предыдущего размещения
    new_placement='internat',     # Размещён в интернате
    old_department=None,
    new_department=department_1,
    old_room=None,
    new_room='101',
    reason='Первичное заселение',
    date=date(2026, 1, 15),
    changed_by=user
)
```

### 5.2 Перевод между отделениями

```
┌──────────────────────────────────────────────────────────────┐
│  СОБЫТИЕ: Перевод                                            │
├──────────────────────────────────────────────────────────────┤
│  До:    department=Отделение_1, room=101                     │
│  После: department=Отделение_2, room=205                     │
│  Дата:  01.03.2026                                           │
│  Примечание: По состоянию здоровья                           │
└──────────────────────────────────────────────────────────────┘
```

**Запись в истории:**
```python
RecipientHistory.objects.create(
    recipient=recipient,
    old_placement='internat',
    new_placement='internat',     # Размещение не изменилось
    old_department=department_1,
    new_department=department_2,
    old_room='101',
    new_room='205',
    reason='По состоянию здоровья',
    date=date(2026, 3, 1),
    changed_by=user
)
```

### 5.3 Временное выбытие в отпуск

```
┌──────────────────────────────────────────────────────────────┐
│  СОБЫТИЕ: Временное выбытие (placement_change)               │
├──────────────────────────────────────────────────────────────┤
│  До:    placement=internat, department=Отделение_1, room=101 │
│  После: placement=vacation, department=None, room=None       │
│  Дата:  10.03.2026                                           │
│  Примечание: Ежегодный отпуск на 14 дней                     │
└──────────────────────────────────────────────────────────────┘
```

**Запись в истории:**
```python
RecipientHistory.objects.create(
    recipient=recipient,
    old_placement='internat',
    new_placement='vacation',
    old_department=department_1,
    new_department=None,          # Отделение очищается
    old_room='101',
    new_room=None,
    reason='Ежегодный отпуск на 14 дней',
    date=date(2026, 3, 10),
    changed_by=user
)
```

### 5.4 Возвращение из отпуска

```
┌──────────────────────────────────────────────────────────────┐
│  СОБЫТИЕ: Возвращение (placement_change)                     │
├──────────────────────────────────────────────────────────────┤
│  До:    placement=vacation, department=None, room=None       │
│  После: placement=internat, department=Отделение_1, room=101 │
│  Дата:  24.03.2026                                           │
│  Примечание: Возвращение из отпуска                          │
└──────────────────────────────────────────────────────────────┘
```

### 5.5 Госпитализация

```
┌──────────────────────────────────────────────────────────────┐
│  СОБЫТИЕ: Госпитализация (placement_change)                  │
├──────────────────────────────────────────────────────────────┤
│  До:    placement=internat, department=Отделение_1, room=101 │
│  После: placement=hospital, department=None, room=None       │
│  Дата:  05.04.2026                                           │
│  Примечание: Госпитализация в городскую больницу             │
└──────────────────────────────────────────────────────────────┘
```

### 5.6 Окончательное выбытие (смерть)

```
┌──────────────────────────────────────────────────────────────┐
│  СОБЫТИЕ: Выбытие (discharge)                                │
├──────────────────────────────────────────────────────────────┤
│  До:    placement=internat, department=Отделение_1, room=101 │
│  После: placement=discharged, department=None, room=None     │
│  Дата:  20.05.2026                                           │
│  Примечание: Смерть                                          │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. API и методы

### 6.1 Получение актуального состояния

Модель `Recipient` предоставляет методы для получения актуальных данных:

```python
# Актуальное размещение на сегодня
recipient.get_current_placement()

# Актуальное отделение (только для internat)
recipient.get_current_department()

# Актуальная комната (только для internat)
recipient.get_current_room()
```

**Логика определения актуальности:**

```python
def get_current_placement(self):
    """
    Возвращает актуальное размещение на основе самой поздней даты в истории.
    Если записей истории нет - возвращает текущее поле placement.
    """
    latest_history = self.history.filter(date__lte=date.today()).order_by('-date').first()
    
    if latest_history and latest_history.new_placement:
        return latest_history.new_placement
    
    return self.placement
```

### 6.2 Регистрация изменений

**Метод `register_placement_change`:**

```python
recipient.register_placement_change(
    old_department=old_dept,
    new_department=new_dept,
    old_room='101',
    new_room='205',
    old_status='internat',
    new_status='internat',
    reason='Перевод по состоянию здоровья',
    date=date.today(),
    user=request.user
)
```

### 6.3 Принцип "одна запись — одна дата"

При создании новой записи с определённой датой система автоматически удаляет существующие записи с той же датой:

```python
# Удаляем существующие записи с той же датой
RecipientHistory.objects.filter(
    recipient=self,
    date=date
).delete()

# Создаем новую запись
RecipientHistory.objects.create(...)
```

Это позволяет корректировать записи без дублирования.

---

## 7. Интерфейс пользователя

### 7.1 Карточка проживающего

В карточке проживающего отображается:

1. **Текущее состояние** — определяется на основе актуальных данных
2. **История изменений** — таблица с хронологией событий
3. **Форма изменения** — модальное окно для изменения статуса

### 7.2 Форма изменения статуса

Поля формы:

| Поле | Описание |
|------|----------|
| `placement` | Выбор типа размещения (интернат/отпуск/больница/выбыл) |
| `department` | Отделение (показывается только для internat) |
| `room` | Комната (показывается только для internat) |
| `date` | Дата изменения (по умолчанию сегодня) |
| `reason` | Причина/комментарий |

### 7.3 Отображение истории

Таблица истории содержит:

| Колонка | Содержимое |
|---------|------------|
| Дата | Дата изменения |
| Событие | Тип события (заселение, перевод и т.д.) |
| Было | Предыдущее значение |
| Стало | Новое значение |
| Причина | Комментарий |
| Автор | Кто внёс изменения |

---

## 8. Особенности реализации

### 8.1 Будущие даты

Если указана дата в будущем:
- Запись в истории создаётся сразу
- Текущие поля `placement`, `department`, `room` **не обновляются**
- Актуальное состояние определяется по истории с датой ≤ сегодня

```python
should_update_current = status_change_date >= today

if should_update_current:
    recipient.placement = new_placement
    recipient.department = new_department
    recipient.room = new_room
```

### 8.2 Обратная совместимость

Для совместимости со старым кодом сохранены:
- Поле `placement` в модели `Recipient`
- Поля `old_status` / `new_status` в модели `RecipientHistory`
- Свойство `status` как алиас для `placement`

### 8.3 Права доступа

- **Администраторы и HR** — полный доступ ко всем изменениям
- **Специалисты и медики** — только просмотр, без права изменения статуса

---

## 9. Диаграмма состояний

```
                    ┌─────────────┐
                    │   Заселение  │
                    └──────┬──────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│                    ИТЕРНАТ                          │
│   (placement=internat, department=X, room=Y)        │
└─────┬───────────────────────────────────────┬───────┘
      │                                       │
      │ Отпуск                                │ Госпитализация
      ▼                                       ▼
┌─────────────┐                       ┌─────────────┐
│   ОТПУСК    │                       │  БОЛЬНИЦА   │
│  (vacation) │                       │  (hospital) │
└──────┬──────┘                       └──────┬──────┘
       │                                     │
       │ Возвращение                         │ Выписка
       └──────────────┬──────────────────────┘
                      │
                      ▼
              ┌─────────────┐
              │   ИТЕРНАТ   │
              └──────┬──────┘
                     │
                     │ Выбытие
                     ▼
              ┌─────────────┐
              │   ВЫБЫЛ     │
              │ (discharged)│
              └─────────────┘
```

---

## 10. Примеры SQL-запросов

### 10.1 Получение актуального состояния на дату

```sql
SELECT 
    r.id,
    r.full_name,
    h.new_placement,
    d.name as department,
    h.new_room
FROM recipients_recipient r
LEFT JOIN LATERAL (
    SELECT * FROM recipients_recipienthistory 
    WHERE recipient_id = r.id 
    AND date <= CURRENT_DATE 
    ORDER BY date DESC 
    LIMIT 1
) h ON true
LEFT JOIN core_department d ON h.new_department_id = d.id;
```

### 10.1 История перемещений за период

```sql
SELECT 
    r.full_name,
    h.date,
    h.old_placement,
    h.new_placement,
    d1.name as old_department,
    d2.name as new_department,
    h.reason
FROM recipients_recipienthistory h
JOIN recipients_recipient r ON h.recipient_id = r.id
LEFT JOIN core_department d1 ON h.old_department_id = d1.id
LEFT JOIN core_department d2 ON h.new_department_id = d2.id
WHERE h.date BETWEEN '2026-01-01' AND '2026-03-31'
ORDER BY h.date DESC;
```
