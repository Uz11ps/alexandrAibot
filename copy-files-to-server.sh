#!/bin/bash

# Скрипт для копирования файлов на сервер (Linux/Mac)

SERVER_IP="95.163.226.186"
SERVER_USER="root"
SERVER_PASSWORD="39iRqAW0U8QQOKne"
REMOTE_DIR="/opt/alexandr-profi-bot"

echo "📤 Копирование файлов на сервер..."

# Проверка наличия файлов
if [ ! -f ".env" ]; then
    echo "❌ Ошибка: файл .env не найден!"
    exit 1
fi

if [ ! -f "credentials/google-credentials.json" ]; then
    echo "❌ Ошибка: файл credentials/google-credentials.json не найден!"
    exit 1
fi

# Установка sshpass (если нужно)
if ! command -v sshpass &> /dev/null; then
    echo "⚠️  sshpass не установлен. Установите его:"
    echo "   Linux: sudo apt-get install sshpass"
    echo "   macOS: brew install hudochenkov/sshpass/sshpass"
    exit 1
fi

# Копирование .env
echo "📄 Копирование .env..."
sshpass -p "$SERVER_PASSWORD" scp -o StrictHostKeyChecking=no .env "${SERVER_USER}@${SERVER_IP}:${REMOTE_DIR}/.env"
if [ $? -eq 0 ]; then
    echo "✅ .env скопирован успешно"
else
    echo "❌ Ошибка при копировании .env"
fi

# Создание директории credentials на сервере
echo "📁 Создание директории credentials..."
sshpass -p "$SERVER_PASSWORD" ssh -o StrictHostKeyChecking=no "${SERVER_USER}@${SERVER_IP}" "mkdir -p ${REMOTE_DIR}/credentials"

# Копирование google-credentials.json
echo "📄 Копирование google-credentials.json..."
sshpass -p "$SERVER_PASSWORD" scp -o StrictHostKeyChecking=no "credentials/google-credentials.json" "${SERVER_USER}@${SERVER_IP}:${REMOTE_DIR}/credentials/google-credentials.json"
if [ $? -eq 0 ]; then
    echo "✅ google-credentials.json скопирован успешно"
else
    echo "❌ Ошибка при копировании google-credentials.json"
fi

echo ""
echo "✅ Готово! Файлы скопированы на сервер."

