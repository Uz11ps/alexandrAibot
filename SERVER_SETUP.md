# Инструкция по установке Docker на сервере

## Быстрая установка

Выполните на сервере:

```bash
# Установка Docker (официальный способ)
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Запуск Docker
systemctl start docker
systemctl enable docker

# Проверка
docker --version
```

## Установка Docker Compose

Docker Compose теперь входит в Docker как плагин. Используйте команду:

```bash
docker compose version
```

**Важно:** Используйте `docker compose` (без дефиса), а не `docker-compose`.

## После установки

```bash
cd /opt/alexandr-profi-bot

# Сборка образа
docker compose build

# Запуск в фоновом режиме
docker compose up -d

# Просмотр логов
docker compose logs -f
```

## Если нужен старый docker-compose

Если по какой-то причине нужен старый `docker-compose` (с дефисом):

```bash
# Установка старой версии docker-compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
docker-compose --version
```

Но рекомендуется использовать новый `docker compose` (без дефиса).

