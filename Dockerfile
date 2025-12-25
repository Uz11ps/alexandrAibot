FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Создание необходимых директорий
RUN mkdir -p storage/photos storage/drafts storage/laws storage/memes storage/services storage/archive \
    credentials config data

# Переменные окружения (будут переопределены через docker-compose или .env)
ENV PYTHONUNBUFFERED=1

# Запуск приложения
CMD ["python", "main.py"]

