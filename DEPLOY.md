# Инструкция по деплою на сервер

## Подготовка

1. Убедитесь, что на локальной машине установлены:
   - Git
   - Docker (опционально, для локального тестирования)
   - SSH доступ к серверу

## Шаг 1: Подготовка репозитория

1. Инициализируйте Git репозиторий (если еще не сделано):
```bash
git init
git add .
git commit -m "Initial commit"
```

2. Создайте репозиторий на GitHub/GitLab и добавьте remote:
```bash
git remote add origin <URL_ВАШЕГО_РЕПОЗИТОРИЯ>
git push -u origin main
```

## Шаг 2: Настройка на сервере

### Подключение к серверу:
```bash
ssh root@95.163.226.186
# Пароль: 39iRqAW0U8QQOKne
```

### Установка Docker и Docker Compose на сервере:

```bash
# Обновление системы
apt-get update && apt-get upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
systemctl start docker
systemctl enable docker

# Установка Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Проверка установки
docker --version
docker-compose --version
```

### Клонирование репозитория:

```bash
cd /opt
git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ> alexandr-profi-bot
cd alexandr-profi-bot
```

### Создание файла .env на сервере:

```bash
nano .env
```

Скопируйте содержимое вашего локального `.env` файла и вставьте в редактор.

**ВАЖНО:** Убедитесь, что файл `.env` не попал в Git (он должен быть в `.gitignore`).

## Шаг 3: Запуск приложения

```bash
# Сборка и запуск контейнера
docker-compose build
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка (если нужно)
docker-compose down
```

## Шаг 4: Автоматический деплой (опционально)

Используйте скрипт `deploy.sh` для автоматического деплоя:

```bash
chmod +x deploy.sh
./deploy.sh
```

**Примечание:** Для работы скрипта нужен `sshpass`:
- Linux: `sudo apt-get install sshpass`
- macOS: `brew install hudochenkov/sshpass/sshpass`

## Полезные команды

### Просмотр логов:
```bash
docker-compose logs -f bot
```

### Перезапуск контейнера:
```bash
docker-compose restart bot
```

### Обновление кода:
```bash
cd /opt/alexandr-profi-bot
git pull
docker-compose build
docker-compose up -d
```

### Проверка статуса:
```bash
docker-compose ps
```

## Безопасность

1. **НЕ коммитьте** файл `.env` в Git
2. Измените пароль SSH на сервере
3. Настройте firewall (если нужно)
4. Используйте SSH ключи вместо паролей

## Troubleshooting

### Проблемы с правами доступа:
```bash
chmod -R 755 storage/
chmod -R 755 credentials/
```

### Проблемы с Docker:
```bash
# Перезапуск Docker
systemctl restart docker

# Очистка старых контейнеров
docker system prune -a
```

### Просмотр логов ошибок:
```bash
docker-compose logs --tail=100 bot
```

