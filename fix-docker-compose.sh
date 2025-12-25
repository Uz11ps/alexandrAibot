#!/bin/bash

# Скрипт для исправления проблемы с docker-compose на сервере

SERVER_IP="95.163.226.186"
SERVER_USER="root"
SERVER_PASSWORD="39iRqAW0U8QQOKne"
REMOTE_DIR="/opt/alexandr-profi-bot"

echo "🔧 Исправление проблемы с docker-compose на сервере..."

# Установка sshpass если не установлен
if ! command -v sshpass &> /dev/null; then
    echo "Установка sshpass..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get update && sudo apt-get install -y sshpass
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install hudochenkov/sshpass/sshpass
    fi
fi

# Исправление на сервере
sshpass -p "$SERVER_PASSWORD" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
    echo "🔍 Проверка установленного Docker..."
    docker --version
    
    echo ""
    echo "🔍 Проверка docker-compose..."
    if command -v docker-compose &> /dev/null; then
        echo "✅ docker-compose установлен"
        docker-compose --version
    elif docker compose version &> /dev/null; then
        echo "✅ docker compose (плагин) доступен"
        docker compose version
    else
        echo "❌ docker-compose не найден, устанавливаем..."
        
        # Установка docker-compose
        curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
        
        # Проверка установки
        docker-compose --version
        
        echo "✅ docker-compose установлен"
    fi
    
    echo ""
    echo "🚀 Теперь можно обновить проект..."
    cd /opt/alexandr-profi-bot
    
    # Определяем команду для использования
    if command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker-compose"
    else
        DOCKER_COMPOSE_CMD="docker compose"
    fi
    
    echo "Используем команду: $DOCKER_COMPOSE_CMD"
    
    echo "🛑 Остановка текущего контейнера..."
    $DOCKER_COMPOSE_CMD down
    
    echo "🔨 Пересборка Docker образа..."
    $DOCKER_COMPOSE_CMD build
    
    echo "🚀 Запуск обновленного контейнера..."
    $DOCKER_COMPOSE_CMD up -d
    
    echo "📋 Просмотр логов (последние 50 строк)..."
    sleep 2
    $DOCKER_COMPOSE_CMD logs --tail=50 bot
    
    echo ""
    echo "✅ Обновление завершено!"
    echo "📊 Статус контейнеров:"
    $DOCKER_COMPOSE_CMD ps
ENDSSH

echo ""
echo "✅ Готово!"

