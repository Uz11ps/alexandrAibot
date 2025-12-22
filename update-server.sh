#!/bin/bash

# Скрипт для обновления проекта на сервере

SERVER_IP="95.163.226.186"
SERVER_USER="root"
SERVER_PASSWORD="39iRqAW0U8QQOKne"
REMOTE_DIR="/opt/alexandr-profi-bot"

echo "🔄 Начало обновления проекта на сервере..."

# Установка sshpass если не установлен
if ! command -v sshpass &> /dev/null; then
    echo "Установка sshpass..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get update && sudo apt-get install -y sshpass
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install hudochenkov/sshpass/sshpass
    fi
fi

# Обновление на сервере
echo "📥 Получение обновлений из Git и пересборка..."
sshpass -p "$SERVER_PASSWORD" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
    cd /opt/alexandr-profi-bot
    
    echo "📥 Получение последних изменений из Git..."
    git pull origin main
    
    echo "🛑 Остановка текущего контейнера..."
    docker-compose down
    
    echo "🔨 Пересборка Docker образа..."
    docker-compose build --no-cache
    
    echo "🚀 Запуск обновленного контейнера..."
    docker-compose up -d
    
    echo "📋 Просмотр логов (последние 50 строк)..."
    sleep 2
    docker-compose logs --tail=50 bot
    
    echo ""
    echo "✅ Обновление завершено!"
    echo "📊 Статус контейнеров:"
    docker-compose ps
ENDSSH

echo ""
echo "✅ Обновление завершено!"

