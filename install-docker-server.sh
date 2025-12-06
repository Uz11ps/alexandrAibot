#!/bin/bash

# Скрипт для установки Docker и Docker Compose на сервере

echo "🐳 Установка Docker и Docker Compose..."

# Обновление системы
echo "📦 Обновление системы..."
apt-get update

# Установка необходимых пакетов
echo "📥 Установка необходимых пакетов..."
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Добавление официального GPG ключа Docker
echo "🔑 Добавление GPG ключа Docker..."
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Настройка репозитория Docker
echo "📋 Настройка репозитория Docker..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установка Docker
echo "🐳 Установка Docker..."
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Запуск и автозапуск Docker
echo "🚀 Запуск Docker..."
systemctl start docker
systemctl enable docker

# Проверка установки
echo "✅ Проверка установки..."
docker --version
docker compose version

echo ""
echo "✅ Docker и Docker Compose установлены!"
echo "📝 Теперь можно запустить: docker compose build && docker compose up -d"

