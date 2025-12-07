# Инструкция по копированию файлов на сервер

## Способ 1: Автоматический (рекомендуется)

### Windows (PowerShell):

```powershell
# Запустите скрипт
.\copy-files-to-server.ps1
```

### Linux/Mac:

```bash
chmod +x copy-files-to-server.sh
./copy-files-to-server.sh
```

## Способ 2: Ручной через SCP

### Windows (PowerShell с sshpass):

```powershell
# Установите sshpass (если нужно)
# Через Chocolatey: choco install sshpass
# Или скачайте: https://github.com/ndbecker/win32-sshpass

# Копирование .env
scp .env root@95.163.226.186:/opt/alexandr-profi-bot/.env

# Копирование google-credentials.json
scp credentials/google-credentials.json root@95.163.226.186:/opt/alexandr-profi-bot/credentials/google-credentials.json
```

### Linux/Mac:

```bash
# Копирование .env
scp .env root@95.163.226.186:/opt/alexandr-profi-bot/.env

# Копирование google-credentials.json
scp credentials/google-credentials.json root@95.163.226.186:/opt/alexandr-profi-bot/credentials/google-credentials.json
```

## Способ 3: Ручной через SSH (если SCP недоступен)

### Шаг 1: Подключитесь к серверу

```bash
ssh root@95.163.226.186
# Пароль: 39iRqAW0U8QQOKne
```

### Шаг 2: Создайте файл .env

```bash
cd /opt/alexandr-profi-bot
nano .env
```

**Скопируйте содержимое вашего локального `.env` файла** и вставьте в редактор.

Нажмите:
- `Ctrl+O` - сохранить
- `Enter` - подтвердить
- `Ctrl+X` - выйти

### Шаг 3: Создайте директорию credentials

```bash
mkdir -p credentials
```

### Шаг 4: Создайте файл google-credentials.json

```bash
nano credentials/google-credentials.json
```

**Скопируйте содержимое вашего локального `credentials/google-credentials.json`** и вставьте в редактор.

Нажмите:
- `Ctrl+O` - сохранить
- `Enter` - подтвердить
- `Ctrl+X` - выйти

### Шаг 5: Проверьте права доступа

```bash
chmod 600 .env
chmod 600 credentials/google-credentials.json
```

## Способ 4: Через WinSCP (Windows GUI)

1. Скачайте и установите WinSCP: https://winscp.net/
2. Подключитесь к серверу:
   - Host: `95.163.226.186`
   - Username: `root`
   - Password: `39iRqAW0U8QQOKne`
3. Перейдите в `/opt/alexandr-profi-bot`
4. Скопируйте файлы `.env` и `credentials/google-credentials.json` с локальной машины

## Проверка после копирования

На сервере выполните:

```bash
cd /opt/alexandr-profi-bot
ls -la .env
ls -la credentials/google-credentials.json
```

Оба файла должны существовать и иметь правильные права доступа.

