@echo off
chcp 65001 >nul
echo ========================================
echo   Запуск сервера социальных услуг
echo ========================================
echo.

cd /d "%~dp0"

echo Проверка миграций...
python manage.py migrate

echo.
echo Запуск сервера на http://127.0.0.1:8080
echo Для остановки нажмите Ctrl+C
echo.

python manage.py runserver 8080

pause
