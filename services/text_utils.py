"""Утилиты для работы с текстом"""
import re
from typing import Optional


def truncate_text_by_sentences(text: str, max_length: int) -> str:
    """
    Обрезает текст до максимальной длины, завершая последнее предложение
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина
        
    Returns:
        Обрезанный текст с завершенным последним предложением
    """
    if len(text) <= max_length:
        return text
    
    # Обрезаем до максимальной длины
    truncated = text[:max_length]
    
    # Ищем последнее завершенное предложение (точка, восклицательный или вопросительный знак)
    # Ищем в последних 30% текста для оптимизации
    search_start = max(0, int(len(truncated) * 0.7))
    last_sentence_end = -1
    
    # Ищем знаки окончания предложения
    for i in range(len(truncated) - 1, search_start - 1, -1):
        if truncated[i] in '.!?':
            # Проверяем, что после знака идет пробел или конец строки
            if i == len(truncated) - 1 or truncated[i + 1] in ' \n\t':
                last_sentence_end = i
                break
    
    # Если нашли конец предложения, обрезаем там
    if last_sentence_end > search_start:
        return truncated[:last_sentence_end + 1]
    
    # Если не нашли, ищем последний пробел или перенос строки
    last_space = truncated.rfind(' ')
    last_newline = truncated.rfind('\n')
    last_break = max(last_space, last_newline)
    
    if last_break > search_start:
        return truncated[:last_break]
    
    # В крайнем случае возвращаем обрезанный текст
    return truncated


def split_text_into_sentences(text: str) -> list[str]:
    """
    Разбивает текст на предложения
    
    Args:
        text: Исходный текст
        
    Returns:
        Список предложений
    """
    # Используем регулярное выражение для разбиения по знакам препинания
    sentences = re.split(r'([.!?]+)', text)
    result = []
    for i in range(0, len(sentences) - 1, 2):
        if i + 1 < len(sentences):
            sentence = sentences[i] + sentences[i + 1]
            if sentence.strip():
                result.append(sentence.strip())
    return result


def extract_paragraph_number(edits: str) -> Optional[int]:
    """
    Извлекает номер абзаца из текста правок
    
    Args:
        edits: Текст правок
        
    Returns:
        Номер абзаца (1-4) или None если не найден
    """
    # Ищем упоминания абзацев: "3 абзац", "третий абзац", "3-й абзац", "абзац 3"
    patterns = [
        r'(\d+)[\s-]*й?\s*абзац',
        r'абзац\s*(\d+)',
        r'(\d+)[\s-]*й?\s*параграф',
        r'параграф\s*(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, edits.lower())
        if match:
            num = int(match.group(1))
            if 1 <= num <= 4:
                return num
    
    # Ищем словами: "первый", "второй", "третий", "четвертый"
    word_to_num = {
        'первый': 1,
        'второй': 2,
        'третий': 3,
        'четвертый': 4,
        'четвёртый': 4
    }
    
    for word, num in word_to_num.items():
        if word in edits.lower():
            return num
    
    return None

