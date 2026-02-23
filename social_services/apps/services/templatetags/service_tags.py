from django import template
from datetime import date

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Получить значение из словаря по ключу"""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def get_range(value):
    """Возвращает range(1, value+1) для итерации в шаблоне"""
    return range(1, value + 1)


@register.filter
def get_range_range(value):
    """Возвращает range(value) для итерации в шаблоне (без +1)"""
    return range(value)


@register.filter
def get_nested_item(dictionary, args):
    """Получить значение из вложенного словаря по двум ключам: dict[key1][key2]"""
    if dictionary is None:
        return None
    try:
        key1, key2 = args.split(',')
        key1 = int(key1)
        key2 = int(key2)
        if key1 in dictionary and key2 in dictionary[key1]:
            return dictionary[key1][key2]
        return None
    except (ValueError, TypeError, KeyError):
        return None


@register.filter
def age_ending(age):
    """Возвращает правильное окончание для возраста: год/года/лет"""
    if age is None:
        return ''
    age = int(age)
    if age % 10 == 1 and age % 100 != 11:
        return 'год'
    elif 2 <= age % 10 <= 4 and not (12 <= age % 100 <= 14):
        return 'года'
    else:
        return 'лет'


@register.filter
def years_living(admission_date):
    """Вычисляет количество лет проживания от даты заселения"""
    if admission_date is None:
        return None
    today = date.today()
    years = today.year - admission_date.year
    if (today.month, today.day) < (admission_date.month, admission_date.day):
        years -= 1
    return years


    

@register.filter
def category_total(items):
    """Вычисляет сумму по категории услуг"""
    total = 0
    for item in items:
        total += float(item.get('total', 0) or 0)
    return f'{total:.2f}'
