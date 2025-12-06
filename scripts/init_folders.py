"""Скрипт для инициализации структуры папок"""
import os
from pathlib import Path

folders = [
    "storage/photos",
    "storage/drafts",
    "storage/laws",
    "storage/memes",
    "storage/services",
    "storage/archive",
    "data"
]

def init_folders():
    """Создает необходимые папки"""
    for folder in folders:
        Path(folder).mkdir(parents=True, exist_ok=True)
        print(f"✓ Папка {folder} создана")

if __name__ == "__main__":
    print("Инициализация структуры папок...")
    init_folders()
    print("Готово!")

