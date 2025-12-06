#!/bin/bash

# Скрипт для первоначальной настройки сервера

echo "🔧 Настройка сервера для деплоя бота..."

# Обновление системы
echo "📦 Обновление системы..."
apt-get update && apt-get upgrade -y

# Установка необходимых пакетов
echo "📥 Установка необходимых пакетов..."
apt-get install -y \
    curl \
    git \
    nano \
    htop \
    ufw

# Установка Docker
echo "🐳 Установка Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    systemctl start docker
    systemctl enable docker
    echo "✅ Docker установлен"
else
    echo "✅ Docker уже установлен"
fi

# Установка Docker Compose
echo "🐳 Установка Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose установлен"
else
    echo "✅ Docker Compose уже установлен"
fi

# Создание директории для проекта
echo "📁 Создание директории проекта..."
mkdir -p /opt/alexandr-profi-bot
cd /opt/alexandr-profi-bot

# Настройка firewall (опционально)
echo "🔥 Настройка firewall..."
ufw allow 22/tcp
ufw --force enable

echo "✅ Сервер настроен!"
echo "📝 Следующие шаги:"
echo "1. Склонируйте репозиторий: git clone <URL> /opt/alexandr-profi-bot"
echo "2. Создайте файл .env с необходимыми переменными"
echo "3. Запустите: docker-compose up -d"

