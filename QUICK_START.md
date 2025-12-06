# Быстрый старт - Деплой на сервер

## Шаг 1: Подготовка Git репозитория

```bash
# Инициализация Git (уже сделано)
git add .
git commit -m "Initial commit with Docker support"

# Создайте репозиторий на GitHub/GitLab и выполните:
git remote add origin <URL_ВАШЕГО_РЕПОЗИТОРИЯ>
git push -u origin main
```

## Шаг 2: Настройка сервера

### Вариант А: Автоматическая настройка

```bash
# Скопируйте server-setup.sh на сервер и выполните:
scp server-setup.sh root@95.163.226.186:/root/
ssh root@95.163.226.186
chmod +x server-setup.sh
./server-setup.sh
```

### Вариант Б: Ручная настройка

```bash
# Подключитесь к серверу
ssh root@95.163.226.186
# Пароль: 39iRqAW0U8QQOKne

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
systemctl start docker
systemctl enable docker

# Установка Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
```

## Шаг 3: Клонирование и настройка проекта

```bash
# На сервере
cd /opt
git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ> alexandr-profi-bot
cd alexandr-profi-bot

# Создайте файл .env (скопируйте с локальной машины или создайте вручную)
nano .env
# Вставьте все переменные из вашего локального .env файла
```

## Шаг 4: Запуск

```bash
# Сборка и запуск
docker-compose build
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Для остановки
docker-compose down
```

## Шаг 5: Автоматический деплой (опционально)

На локальной машине:

```bash
# Установите sshpass (если нужно)
# Linux: sudo apt-get install sshpass
# macOS: brew install hudochenkov/sshpass/sshpass

# Запустите скрипт деплоя
chmod +x deploy.sh
./deploy.sh
```

## Полезные команды

```bash
# Просмотр логов
docker-compose logs -f bot

# Перезапуск
docker-compose restart bot

# Обновление кода
cd /opt/alexandr-profi-bot
git pull
docker-compose build
docker-compose up -d

# Проверка статуса
docker-compose ps

# Вход в контейнер
docker-compose exec bot bash
```

## Важно!

1. **НЕ коммитьте** файл `.env` в Git
2. Убедитесь, что все секретные данные в `.env` на сервере
3. Файл `.env` должен быть создан на сервере вручную

## Troubleshooting

Если что-то не работает:

1. Проверьте логи: `docker-compose logs -f`
2. Проверьте права доступа: `chmod -R 755 storage/ credentials/`
3. Перезапустите Docker: `systemctl restart docker`
4. Пересоберите контейнер: `docker-compose build --no-cache`

