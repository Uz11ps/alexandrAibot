# Инструкция по обновлению проекта на сервере

## Быстрый способ (автоматический скрипт)

Используйте скрипт `update-server.sh` для автоматического обновления:

```bash
./update-server.sh
```

Скрипт выполнит:
1. Подключение к серверу
2. Получение последних изменений из Git (`git pull`)
3. Остановку текущего контейнера
4. Пересборку Docker образа
5. Запуск обновленного контейнера
6. Показ логов

---

## Ручной способ (через SSH)

### Шаг 1: Подключение к серверу

```bash
ssh root@95.163.226.186
# Пароль: 39iRqAW0U8QQOKne
```

### Шаг 2: Переход в директорию проекта

```bash
cd /opt/alexandr-profi-bot
```

### Шаг 3: Получение обновлений из Git

```bash
git pull origin main
```

### Шаг 4: Остановка текущего контейнера

```bash
docker-compose down
```

### Шаг 5: Пересборка Docker образа

**Вариант 1: Обычная пересборка (быстрее, использует кэш)**
```bash
docker-compose build
```

**Вариант 2: Полная пересборка без кэша (если есть проблемы)**
```bash
docker-compose build --no-cache
```

### Шаг 6: Запуск обновленного контейнера

```bash
docker-compose up -d
```

### Шаг 7: Проверка логов

```bash
# Просмотр последних 50 строк логов
docker-compose logs --tail=50 bot

# Или просмотр логов в реальном времени
docker-compose logs -f bot
```

### Шаг 8: Проверка статуса

```bash
docker-compose ps
```

---

## Полезные команды

### Просмотр логов
```bash
# Последние 100 строк
docker-compose logs --tail=100 bot

# В реальном времени
docker-compose logs -f bot

# Логи за последний час
docker-compose logs --since 1h bot
```

### Перезапуск контейнера (без пересборки)
```bash
docker-compose restart bot
```

### Остановка контейнера
```bash
docker-compose down
```

### Запуск контейнера
```bash
docker-compose up -d
```

### Проверка статуса
```bash
docker-compose ps
```

### Очистка старых образов (освобождение места)
```bash
docker system prune -a
```

---

## Решение проблем

### Если контейнер не запускается

1. Проверьте логи:
```bash
docker-compose logs bot
```

2. Проверьте статус:
```bash
docker-compose ps
```

3. Попробуйте пересобрать без кэша:
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Если есть проблемы с правами доступа

```bash
chmod -R 755 storage/
chmod -R 755 credentials/
chmod -R 755 config/
```

### Если нужно полностью пересоздать контейнер

```bash
docker-compose down
docker-compose rm -f
docker-compose build --no-cache
docker-compose up -d
```

### Если нужно очистить все и начать заново

```bash
docker-compose down
docker-compose rm -f
docker rmi alexandr-profi-bot_bot
docker-compose build --no-cache
docker-compose up -d
```

---

## Проверка обновления модели GPT-5

После обновления проверьте, что модель изменилась:

```bash
# Просмотр логов при запуске
docker-compose logs bot | grep -i "gpt-5\|model"

# Или проверьте конфигурацию
docker-compose exec bot cat config/settings.py | grep OPENAI_MODEL
```

---

## Автоматизация (опционально)

Можно настроить автоматическое обновление через cron:

```bash
# Редактирование crontab
crontab -e

# Добавить строку для ежедневного обновления в 3:00 ночи
0 3 * * * cd /opt/alexandr-profi-bot && git pull origin main && docker-compose down && docker-compose build && docker-compose up -d
```

---

## Важные замечания

1. **Файл .env**: Убедитесь, что файл `.env` на сервере содержит актуальные настройки и не перезаписывается при `git pull`

2. **Данные**: Все данные в папках `storage/`, `credentials/`, `config/`, `data/` сохраняются благодаря volume mounts в docker-compose.yml

3. **Резервное копирование**: Перед обновлением рекомендуется сделать бэкап важных данных:
```bash
cd /opt/alexandr-profi-bot
tar -czf backup-$(date +%Y%m%d-%H%M%S).tar.gz storage/ credentials/ config/ data/
```

