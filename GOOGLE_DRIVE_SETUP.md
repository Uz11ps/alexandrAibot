# Инструкция по настройке Google Drive

## Шаг 1: Создание проекта в Google Cloud Console

1. Перейдите на [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте новый проект или выберите существующий
3. Назовите проект (например: "Arheon Bot")

## Шаг 2: Включение Google Drive API

1. В меню выберите **"APIs & Services"** → **"Library"**
2. Найдите **"Google Drive API"**
3. Нажмите **"Enable"** (Включить)

## Шаг 3: Создание учетных данных (Credentials)

1. Перейдите в **"APIs & Services"** → **"Credentials"**
2. Нажмите **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**
3. Если появится запрос на настройку экрана согласия OAuth:
   - Выберите **"External"** (Внешний)
   - Заполните обязательные поля:
     - Название приложения: "Arheon Bot"
     - Email поддержки: ваш email
     - Email разработчика: ваш email
   - Сохраните и продолжите
4. Выберите тип приложения: **"Desktop app"** (Десктопное приложение)
5. Назовите клиента (например: "Arheon Bot Client")
6. Нажмите **"Create"** (Создать)
7. Скачайте JSON файл с учетными данными

## Шаг 4: Сохранение credentials файла

1. Переименуйте скачанный файл в `google-credentials.json`
2. Создайте папку `credentials` в корне проекта (если её нет)
3. Поместите файл `google-credentials.json` в папку `credentials/`

Структура должна быть:
```
AlexandrProfiStroi/
├── credentials/
│   └── google-credentials.json
├── main.py
└── ...
```

## Шаг 5: Первый запуск и авторизация

1. При первом запуске бота откроется браузер для авторизации
2. Войдите в Google аккаунт, который будет использоваться для доступа к Drive
3. Разрешите доступ приложению к Google Drive
4. После авторизации будет создан файл `credentials/google-token.json`
5. Этот файл сохраняет токены доступа для последующих запусков

## Шаг 6: Создание папок в Google Drive

Создайте следующие папки в Google Drive (или используйте существующие):

1. **Фотографии объектов** - для хранения фото со строительных объектов
2. **Черновики** - для черновиков сотрудников
3. **Законы** - для документов с законами
4. **Мемы** - для мемов и визуального контента
5. **Услуги** - для материалов об услугах компании
6. **Архив** - для архива опубликованных постов

## Шаг 7: Получение ID папок

Для каждой папки нужно получить её ID:

1. Откройте папку в Google Drive
2. Посмотрите URL в адресной строке браузера
3. ID папки находится в URL после `/folders/`
   
   Например, если URL: `https://drive.google.com/drive/folders/1a2b3c4d5e6f7g8h9i0j`
   То ID папки: `1a2b3c4d5e6f7g8h9i0j`

## Шаг 8: Настройка .env файла

Добавьте следующие параметры в файл `.env`:

```env
# Google Drive настройки
GOOGLE_DRIVE_ENABLED=true
GOOGLE_DRIVE_CREDENTIALS_FILE=credentials/google-credentials.json
GOOGLE_DRIVE_TOKEN_FILE=credentials/google-token.json

# ID папок в Google Drive
GOOGLE_DRIVE_PHOTOS_FOLDER_ID=ваш_id_папки_фотографий
GOOGLE_DRIVE_DRAFTS_FOLDER_ID=ваш_id_папки_черновиков
GOOGLE_DRIVE_LAWS_FOLDER_ID=ваш_id_папки_законов
GOOGLE_DRIVE_MEMES_FOLDER_ID=ваш_id_папки_мемов
GOOGLE_DRIVE_SERVICES_FOLDER_ID=ваш_id_папки_услуг
GOOGLE_DRIVE_ARCHIVE_FOLDER_ID=ваш_id_папки_архива
```

## Использование

После настройки администратор может загружать файлы через команду `/upload` в Telegram боте:

1. Отправьте команду `/upload`
2. Выберите тип папки (photos, drafts, laws, memes, services, archive)
3. Отправьте файл (фото или документ)
4. Файл автоматически загрузится в соответствующую папку Google Drive

## Важные замечания

- Убедитесь, что Google аккаунт имеет достаточно места в Drive
- Файлы будут автоматически синхронизироваться между локальным хранилищем и Google Drive
- При генерации постов бот будет использовать файлы из Google Drive, если он включен
- Токены доступа сохраняются в `google-token.json` и автоматически обновляются при необходимости

## Устранение проблем

**Ошибка "Файл credentials не найден":**
- Убедитесь, что файл `google-credentials.json` находится в папке `credentials/`
- Проверьте путь в `.env`: `GOOGLE_DRIVE_CREDENTIALS_FILE`

**Ошибка авторизации:**
- Удалите файл `google-token.json` и запустите бота заново
- Убедитесь, что Google Drive API включен в проекте

**Файлы не загружаются:**
- Проверьте, что ID папок указаны правильно в `.env`
- Убедитесь, что у Google аккаунта есть права на запись в эти папки

