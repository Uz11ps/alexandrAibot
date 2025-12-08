#!/usr/bin/env python3
"""
Прокси-туннель для получения токена VK через прокси
Запустите скрипт и настройте браузер на использование локального прокси 127.0.0.1:8888
"""
import socket
import select
import threading
import base64
import sys

# Настройки прокси
PROXY_HOST = '141.11.169.175'
PROXY_PORT = 58481
PROXY_USER = 'JCQ1RM2Z'
PROXY_PASS = 'SV6CLQ29'

# Локальный прокси сервер
LOCAL_HOST = '127.0.0.1'
LOCAL_PORT = 8888


def create_proxy_auth_header(username, password):
    """Создает заголовок авторизации для прокси"""
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Proxy-Authorization: Basic {encoded}\r\n"


def handle_client(client_socket, client_address):
    """Обрабатывает подключение клиента"""
    try:
        # Получаем запрос от клиента
        request = client_socket.recv(4096).decode('utf-8', errors='ignore')
        
        if not request:
            return
        
        print(f"[{client_address[0]}] Получен запрос")
        
        # Парсим первую строку запроса
        first_line = request.split('\n')[0]
        parts = first_line.split()
        
        if len(parts) < 3:
            return
        
        method = parts[0]
        url = parts[1]
        
        # Подключаемся к прокси
        proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        proxy_socket.settimeout(10)
        
        try:
            proxy_socket.connect((PROXY_HOST, PROXY_PORT))
            print(f"[{client_address[0]}] Подключено к прокси {PROXY_HOST}:{PROXY_PORT}")
        except Exception as e:
            print(f"[{client_address[0]}] Ошибка подключения к прокси: {e}")
            client_socket.close()
            return
        
        # Для HTTP прокси нужно отправить полный запрос с авторизацией
        # Добавляем заголовок авторизации прокси
        auth_header = create_proxy_auth_header(PROXY_USER, PROXY_PASS)
        
        # Модифицируем запрос, добавляя авторизацию прокси
        lines = request.split('\n')
        modified_request = lines[0] + '\n' + auth_header
        
        # Добавляем остальные заголовки
        for line in lines[1:]:
            if line.strip() and not line.lower().startswith('proxy-authorization'):
                modified_request += line
        
        # Отправляем запрос через прокси
        proxy_socket.sendall(modified_request.encode('utf-8'))
        
        # Пересылаем данные между клиентом и прокси
        while True:
            readable, _, exceptional = select.select(
                [client_socket, proxy_socket], [], [client_socket, proxy_socket], 5
            )
            
            if exceptional:
                break
            
            if not readable:
                continue
            
            for sock in readable:
                try:
                    data = sock.recv(4096)
                    if not data:
                        return
                    
                    if sock is client_socket:
                        proxy_socket.sendall(data)
                    else:
                        client_socket.sendall(data)
                except Exception as e:
                    print(f"[{client_address[0]}] Ошибка передачи данных: {e}")
                    return
    
    except Exception as e:
        print(f"[{client_address[0]}] Ошибка: {e}")
    finally:
        try:
            client_socket.close()
            proxy_socket.close()
        except:
            pass


def main():
    """Главная функция"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((LOCAL_HOST, LOCAL_PORT))
        server.listen(5)
        print("=" * 60)
        print("Прокси-туннель запущен!")
        print(f"Локальный адрес: {LOCAL_HOST}:{LOCAL_PORT}")
        print(f"Прокси: {PROXY_HOST}:{PROXY_PORT}")
        print("=" * 60)
        print("\nНастройте браузер:")
        print(f"  HTTP прокси: {LOCAL_HOST}:{LOCAL_PORT}")
        print("  Тип: HTTP")
        print("\nИли используйте расширение браузера для прокси")
        print("\nНажмите Ctrl+C для остановки")
        print("=" * 60)
        
        while True:
            client_socket, client_address = server.accept()
            thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address)
            )
            thread.daemon = True
            thread.start()
    
    except KeyboardInterrupt:
        print("\n\nОстановка прокси-туннеля...")
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        server.close()


if __name__ == "__main__":
    main()

