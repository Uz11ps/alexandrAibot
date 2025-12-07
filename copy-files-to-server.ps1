# Скрипт для копирования файлов на сервер
# Использование: .\copy-files-to-server.ps1

$SERVER_IP = "95.163.226.186"
$SERVER_USER = "root"
$SERVER_PASSWORD = "39iRqAW0U8QQOKne"
$REMOTE_DIR = "/opt/alexandr-profi-bot"

Write-Host "📤 Копирование файлов на сервер..." -ForegroundColor Green

# Проверка наличия файлов
if (-not (Test-Path ".env")) {
    Write-Host "❌ Ошибка: файл .env не найден!" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "credentials/google-credentials.json")) {
    Write-Host "❌ Ошибка: файл credentials/google-credentials.json не найден!" -ForegroundColor Red
    exit 1
}

# Установка sshpass (если нужно)
if (-not (Get-Command sshpass -ErrorAction SilentlyContinue)) {
    Write-Host "⚠️  sshpass не установлен. Установите его или используйте команды вручную." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Команды для выполнения на сервере:" -ForegroundColor Cyan
    Write-Host "1. Создайте файл .env:"
    Write-Host "   nano /opt/alexandr-profi-bot/.env"
    Write-Host "   (скопируйте содержимое вашего локального .env файла)"
    Write-Host ""
    Write-Host "2. Создайте директорию credentials:"
    Write-Host "   mkdir -p /opt/alexandr-profi-bot/credentials"
    Write-Host ""
    Write-Host "3. Создайте файл google-credentials.json:"
    Write-Host "   nano /opt/alexandr-profi-bot/credentials/google-credentials.json"
    Write-Host "   (скопируйте содержимое вашего локального credentials/google-credentials.json)"
    exit 0
}

# Копирование .env
Write-Host "📄 Копирование .env..." -ForegroundColor Yellow
$env:SSHPASS = $SERVER_PASSWORD
sshpass -e scp -o StrictHostKeyChecking=no .env "${SERVER_USER}@${SERVER_IP}:${REMOTE_DIR}/.env"
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ .env скопирован успешно" -ForegroundColor Green
} else {
    Write-Host "❌ Ошибка при копировании .env" -ForegroundColor Red
}

# Создание директории credentials на сервере
Write-Host "📁 Создание директории credentials..." -ForegroundColor Yellow
sshpass -e ssh -o StrictHostKeyChecking=no "${SERVER_USER}@${SERVER_IP}" "mkdir -p ${REMOTE_DIR}/credentials"

# Копирование google-credentials.json
Write-Host "📄 Копирование google-credentials.json..." -ForegroundColor Yellow
sshpass -e scp -o StrictHostKeyChecking=no "credentials/google-credentials.json" "${SERVER_USER}@${SERVER_IP}:${REMOTE_DIR}/credentials/google-credentials.json"
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ google-credentials.json скопирован успешно" -ForegroundColor Green
} else {
    Write-Host "❌ Ошибка при копировании google-credentials.json" -ForegroundColor Red
}

Write-Host ""
Write-Host "✅ Готово! Файлы скопированы на сервер." -ForegroundColor Green

