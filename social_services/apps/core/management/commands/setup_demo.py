"""
Management command для загрузки тестовых данных и услуг из tabel.html
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.core.models import Department
from apps.recipients.models import Recipient, Contract, ContractService
from apps.services.models import ServiceCategory, Service


User = get_user_model()


# Данные услуг из tabel.html
SERVICES_DATA = [
    {
        'category': 'социально-бытовые',
        'services': [
            {'code': '1', 'name': 'Обеспечение площадью жилых помещений в соответствии с утвержденными нормативами'},
            {'code': '2', 'name': 'Предоставление помещений для организации реабилитационных мероприятий, лечебно-трудовой деятельности, культурно-бытового обслуживания'},
            {'code': '3', 'name': 'Обеспечение питанием, в соответствии с утвержденными нормативами'},
            {'code': '4', 'name': 'Обеспечением мягким инвентарем (одеждой, обувью, нательным бельем и постельными принадлежностями) в соответствии с утвержденными нормативами'},
            {'code': '5', 'name': 'Обеспечение за счет средств получателя социальных услуг книгами, журналами, газетами, настольными играми'},
            {'code': '6', 'name': 'Содействие в организации предоставления услуг предприятиями торговли, а также в предоставлении информационных услуг'},
            {'code': '7', 'name': 'Обеспечение сохранности личных вещей и ценностей, сданных на хранение'},
            {'code': '8', 'name': 'Создание условий для отправления религиозных обрядов'},
            {'code': '9', 'name': 'Предоставление гигиенических услуг лицам, не способным по состоянию здоровья самостоятельно осуществлять за собой уход', 
             'sub_services': [
                {'code': '9.1', 'name': 'Умывание/помощь при умывании'},
                {'code': '9.2', 'name': 'Купание в кровати/ Купание в приспособленном помещении (месте), включая мытье головы'},
                {'code': '9.3', 'name': 'Гигиеническое обтирание'},
                {'code': '9.4', 'name': 'Мытье головы, в том числе в кровати'},
                {'code': '9.5', 'name': 'Подмывание'},
                {'code': '9.6', 'name': 'Гигиеническая обработка рук и ногтей/Помощь при гигиенической обработке рук и ногтей'},
                {'code': '9.7', 'name': 'Мытье ног'},
                {'code': '9.8', 'name': 'Гигиеническая обработка ног и ногтей'},
                {'code': '9.9', 'name': 'Гигиеническое бритье'},
                {'code': '9.10', 'name': 'Гигиеническая стрижка'},
                {'code': '9.11', 'name': 'Смена одежды (обуви)/Помощь при смене одежды (обуви)'},
                {'code': '9.12', 'name': 'Смена нательного белья/Помощь при смене нательного белья'},
                {'code': '9.13', 'name': 'Смена постельного белья'},
                {'code': '9.14', 'name': 'Смена абсорбирующего белья, включая гигиеническую обработку/Помощь при пользовании туалетом (иными приспособлениями), включая гигиеническую обработку/Замена мочеприемника и (или) калоприемника, включая гигиеническую обработку'},
            ]},
            {'code': '10', 'name': 'Помощь в приеме пищи (кормление)'},
            {'code': '11', 'name': 'Отправка за счет средств получателя социальных услуг почтовой корреспонденции'},
        ]
    },
    {
        'category': 'социально-медицинские',
        'services': [
            {'code': '12', 'name': 'Проведение реабилитационных мероприятий (медицинских, социальных), в том числе для инвалидов на основании индивидуальных программ реабилитации'},
            {'code': '13', 'name': 'Оказание первичной медико-санитарной помощи, в .т.ч.'},
            {'code': '14', 'name': 'Проведение оздоровительных мероприятий'},
            {'code': '15', 'name': 'Проведение мероприятий, направленных на формирование здорового образа жизни'},
            {'code': '16', 'name': 'Проведение занятий по адаптивной физической культуре'},
            {'code': '17', 'name': 'Систематическое наблюдение за получателями социальных услуг в целях выявления отклонений в состоянии здоровья'},
            {'code': '18', 'name': 'Консультирование по социально – медицинским вопросам'},
            {'code': '19', 'name': 'Выполнение процедур, связанных с наблюдением за состоянием здоровья в т.ч.:'},
            {'code': '20', 'name': 'Содействие в прохождение диспансеризации'},
            {'code': '21', 'name': 'Содействие в госпитализации нуждающихся в мед. Организации'},
            {'code': '22', 'name': 'Содействие в направлении по заключению врачей на санаторно – курортное лечение'},
            {'code': '23', 'name': 'Содействие в прохождении медико-социальной экспертизы'},
            {'code': '24', 'name': 'Содействие в обеспечении по заключению врачей лекарственными препаратами для медицинского применения и медицинскими изделиями'},
        ]
    },
    {
        'category': 'социально-психологические',
        'services': [
            {'code': '25', 'name': 'Оказание психологической поддержки, проведение психокоррекционной работы'},
        ]
    },
    {
        'category': 'социально-педагогические',
        'services': [
            {'code': '26', 'name': 'Содействие в организации получения образования'},
            {'code': '27', 'name': 'Социально-педагогическая коррекция, включая диагностику и консультирование'},
            {'code': '28', 'name': 'Формирование позитивных интересов(в том числе в сфере досуга)'},
            {'code': '29', 'name': 'Организация досуга (праздники,экскурсии и другие культурные мероприятия)'},
        ]
    },
    {
        'category': 'социально-трудовые',
        'services': [
            {'code': '30', 'name': 'Проведение мероприятий по использованию трудовых возможностей о обучению доступным профессиональным навыкам'},
            {'code': '31', 'name': 'Организация помощи в получении образования, в том числе профессиональгого образования инвалидами (детьми-инвалидами) в соответствии с их способностями'},
        ]
    },
    {
        'category': 'социально-правовые',
        'services': [
            {'code': '32', 'name': 'Оказание помощи в оформлении и восстановлении утраченных документов получателей социальных услуг'},
            {'code': '33', 'name': 'Оказание помощи в получении юридических услуг (в том числе бесплатно)'},
            {'code': '34', 'name': 'Оказание помощи в защите прав и законных интересов получателей социальных услуг'},
        ]
    },
    {
        'category': 'услуги в целях повышения коммуникатимного потенциала получателей социальных услуг,имеющих ограничения жизнедеятельности,в том числе детей-инвалидов',
        'services': [
            {'code': '35', 'name': 'Обучение инвалидов (детей-инвалидов) пользованию средствами ухода и техническими средствами реабилитации'},
            {'code': '36', 'name': 'Проведение социально-реабилитационных мероприятий в сфере социального обслуживания'},
            {'code': '37', 'name': 'Обучение навыкам поведения в быту и общественных местах'},
            {'code': '38', 'name': 'Оказание помощи в обучении навыкам компьютерной грамотности'},
        ]
    },
]


class Command(BaseCommand):
    help = 'Загружает тестовые данные: отделения, услуги, проживающих'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--no-recipients',
            action='store_true',
            help='Не создавать тестовых проживающих',
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Загрузка тестовых данных...')
        
        # Создаём суперпользователя
        self.create_users()
        
        # Создаём отделения
        self.create_departments()
        
        # Создаём услуги
        self.create_services()
        
        # Создаём проживающих
        if not options['no_recipients']:
            self.create_recipients()
        
        self.stdout.write(self.style.SUCCESS('Данные успешно загружены!'))
    
    def create_users(self):
        self.stdout.write('Создание пользователей...')
        
        # Админ
        if not User.objects.filter(username='admin').exists():
            admin = User.objects.create_superuser(
                username='admin',
                email='admin@example.com',
                password='admin',
                first_name='Администратор',
                role='admin'
            )
            self.stdout.write(f'  Создан админ: admin / admin')
        
        # Кадровик
        if not User.objects.filter(username='hr').exists():
            hr = User.objects.create_user(
                username='hr',
                email='hr@example.com',
                password='hr123',
                first_name='Кадровик',
                last_name='Иванов',
                role='hr'
            )
            self.stdout.write(f'  Создан кадровик: hr / hr123')
        
        # Медики для каждого отделения
        departments_data = [
            ('medic1', 'Медсестра', 'Отделение 1', 1),
            ('medic2', 'Медсестра', 'Отделение 2', 2),
            ('medic3', 'Медсестра', 'Отделение 3', 3),
            ('medic4', 'Медсестра', 'Отделение 4', 4),
            ('mercy', 'Медсестра', 'Милосердие', None),
        ]
        
        for username, first_name, dept_name, dept_num in departments_data:
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(
                    username=username,
                    email=f'{username}@example.com',
                    password=f'{username}123',
                    first_name=first_name,
                    last_name=dept_name,
                    role='medic'
                )
                self.stdout.write(f'  Создан медик: {username} / {username}123')
    
    def create_departments(self):
        self.stdout.write('Создание отделений...')
        
        departments = [
            ('1', 'Отделение №1', False),
            ('2', 'Отделение №2', False),
            ('3', 'Отделение №3', False),
            ('4', 'Отделение №4', False),
            ('mercy', 'Милосердие', True),
        ]
        
        for code, name, is_mercy in departments:
            dept, created = Department.objects.get_or_create(
                code=code,
                defaults={'name': name, 'is_mercy': is_mercy}
            )
            if created:
                self.stdout.write(f'  Создано отделение: {name}')
            
            # Привязываем медиков к отделениям
            User.objects.filter(username=f'medic{code}' if code != 'mercy' else 'mercy').update(department=dept)
    
    def create_services(self):
        self.stdout.write('Создание услуг...')
        
        for cat_order, cat_data in enumerate(SERVICES_DATA):
            category, created = ServiceCategory.objects.get_or_create(
                name=cat_data['category'],
                defaults={'order': cat_order}
            )
            if created:
                self.stdout.write(f'  Создана категория: {cat_data["category"][:50]}...')
            
            for serv_order, serv_data in enumerate(cat_data['services']):
                service, created = Service.objects.get_or_create(
                    code=serv_data['code'],
                    defaults={
                        'name': serv_data['name'],
                        'category': category,
                        'order': serv_order,
                        'price': 0
                    }
                )
                if created:
                    self.stdout.write(f'    Создана услуга: {serv_data["code"]}. {serv_data["name"][:40]}...')
                
                # Создаём подуслуги
                if 'sub_services' in serv_data:
                    for sub_order, sub_data in enumerate(serv_data['sub_services']):
                        sub_service, created = Service.objects.get_or_create(
                            code=sub_data['code'],
                            defaults={
                                'name': sub_data['name'],
                                'category': category,
                                'parent': service,
                                'order': sub_order,
                                'price': 0
                            }
                        )
                        if created:
                            self.stdout.write(f'      Создана подуслуга: {sub_data["code"]}')
    
    def create_recipients(self):
        self.stdout.write('Создание проживающих (500 человек)...')
        
        import random
        from datetime import date, timedelta
        
        # Русские имена и фамилии
        male_first_names = ['Иван', 'Петр', 'Николай', 'Михаил', 'Федор', 'Сергей', 'Александр', 'Василий', 'Анатолий', 'Владимир']
        female_first_names = ['Анна', 'Мария', 'Елена', 'Татьяна', 'Наталья', 'Екатерина', 'Ольга', 'Светлана', 'Галина', 'Зинаида']
        male_last_names = ['Иванов', 'Петров', 'Сидоров', 'Козлов', 'Морозов', 'Волков', 'Соколов', 'Федоров', 'Михайлов', 'Васильев']
        female_last_names = ['Иванова', 'Петрова', 'Сидорова', 'Козлова', 'Морозова', 'Волкова', 'Соколова', 'Федорова', 'Михайлова', 'Васильева']
        patronymics = ['Иванович', 'Петрович', 'Николаевич', 'Михайлович', 'Федорович', 'Александрович', 'Владимирович', 'Васильевич']
        
        departments = list(Department.objects.all())
        statuses = ['active', 'active', 'active', 'active', 'vacation', 'hospital']  # 66% active
        
        created_count = 0
        for i in range(500):
            is_male = random.choice([True, False])
            
            if is_male:
                first_name = random.choice(male_first_names)
                last_name = random.choice(male_last_names)
            else:
                first_name = random.choice(female_first_names)
                last_name = random.choice(female_last_names)
            
            patronymic = random.choice(patronymics) if is_male else random.choice(patronymics).replace('ич', 'на')
            
            # Возраст 60-95 лет
            birth_year = random.randint(1930, 1965)
            birth_month = random.randint(1, 12)
            birth_day = random.randint(1, 28)
            birth_date = date(birth_year, birth_month, birth_day)
            
            # Дата заселения
            admission_year = random.randint(2015, 2024)
            admission_month = random.randint(1, 12)
            admission_day = random.randint(1, 28)
            admission_date = date(admission_year, admission_month, admission_day)
            
            department = random.choice(departments)
            status = random.choice(statuses)
            room = f'{random.randint(1, 4)}{random.randint(1, 20):02d}'
            
            recipient, created = Recipient.objects.get_or_create(
                last_name=last_name,
                first_name=first_name,
                patronymic=patronymic,
                birth_date=birth_date,
                defaults={
                    'department': department,
                    'room': room,
                    'status': status,
                    'admission_date': admission_date,
                }
            )
            
            if created:
                created_count += 1
                
                # Создаём ИППСУ для каждого проживающего
                contract = Contract.objects.create(
                    recipient=recipient,
                    number=f'ИППСУ-{recipient.id:04d}',
                    date_start=admission_date,
                    is_active=True
                )
                
                # Добавляем все услуги в ИППСУ
                all_services = Service.objects.filter(parent__isnull=True)
                for service in all_services[:10]:  # Добавляем первые 10 услуг
                    ContractService.objects.create(
                        contract=contract,
                        service=service
                    )
        
        self.stdout.write(f'  Создано {created_count} проживающих')
