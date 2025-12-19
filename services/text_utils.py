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


def find_paragraphs_by_keywords(text: str, keywords_list: list[str]) -> list[int]:
    """
    Находит номера абзацев по списку ключевых слов (для удаления нескольких абзацев)
    
    Args:
        text: Исходный текст поста
        keywords_list: Список ключевых фраз для поиска абзацев
        
    Returns:
        Список номеров абзацев (1-based)
    """
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    found_indices = []
    
    for keywords in keywords_list:
        keywords_lower = keywords.lower().strip()
        if not keywords_lower:
            continue
            
        # Специальные паттерны для поиска
        if 'техническ' in keywords_lower or 'аспект' in keywords_lower or 'норм' in keywords_lower or 'снип' in keywords_lower:
            for i, para in enumerate(paragraphs, 1):
                para_lower = para.lower()
                if ('техническ' in para_lower or 'норм' in para_lower or 'снип' in para_lower or 'гост' in para_lower) and (i) not in found_indices:
                    found_indices.append(i)
                    break
        
        elif 'ошибк' in keywords_lower:
            for i, para in enumerate(paragraphs, 1):
                para_lower = para.lower()
                if ('ошибк' in para_lower or 'част' in para_lower) and (i) not in found_indices:
                    found_indices.append(i)
                    break
        
        elif 'однако' in keywords_lower or 'сталкиваемся' in keywords_lower:
            for i, para in enumerate(paragraphs, 1):
                para_lower = para.lower()
                if ('однако' in para_lower or 'сталкиваемся' in para_lower) and (i) not in found_indices:
                    found_indices.append(i)
                    break
        
        elif 'работаем строго' in keywords_lower or 'снип' in keywords_lower or 'норматив' in keywords_lower:
            for i, para in enumerate(paragraphs, 1):
                para_lower = para.lower()
                if ('работаем строго' in para_lower or 'снип' in para_lower or 'норматив' in para_lower) and (i) not in found_indices:
                    found_indices.append(i)
                    break
        
        else:
            # Общий поиск по ключевым словам
            keyword_words = [kw.strip() for kw in keywords_lower.split() if len(kw.strip()) > 2]
            for i, para in enumerate(paragraphs, 1):
                para_lower = para.lower()
                matches = sum(1 for kw in keyword_words if kw in para_lower)
                if matches >= max(1, len(keyword_words) * 0.5) and (i) not in found_indices:
                    found_indices.append(i)
                    break
    
    return sorted(set(found_indices))


def find_paragraph_by_keywords(text: str, keywords: str) -> Optional[int]:
    """
    Находит номер абзаца по ключевым словам
    
    Args:
        text: Исходный текст поста
        keywords: Ключевые слова для поиска абзаца
        
    Returns:
        Номер абзаца (1-based) или None если не найден
    """
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    keywords_lower = keywords.lower()
    
    # Разбиваем ключевые слова
    keyword_list = [kw.strip() for kw in keywords_lower.split() if len(kw.strip()) > 2]
    
    # Специальные паттерны для поиска
    if 'техническ' in keywords_lower or 'аспект' in keywords_lower or 'норм' in keywords_lower:
        for i, para in enumerate(paragraphs, 1):
            para_lower = para.lower()
            if 'техническ' in para_lower or 'норм' in para_lower or 'снип' in para_lower or 'гост' in para_lower:
                return i
    
    if 'ошибк' in keywords_lower:
        for i, para in enumerate(paragraphs, 1):
            para_lower = para.lower()
            if 'ошибк' in para_lower or 'част' in para_lower:
                return i
    
    # Общий поиск по ключевым словам
    for i, para in enumerate(paragraphs, 1):
        para_lower = para.lower()
        # Проверяем, содержатся ли ключевые слова в абзаце
        matches = sum(1 for kw in keyword_list if kw in para_lower)
        if matches >= len(keyword_list) * 0.5:  # Хотя бы половина ключевых слов
            return i
    
    return None


def remove_paragraphs_programmatically(text: str, paragraph_nums: list[int]) -> str:
    """
    Программно удаляет указанные абзацы из текста
    
    Args:
        text: Исходный текст
        paragraph_nums: Список номеров абзацев для удаления (1-based), отсортированный по убыванию
        
    Returns:
        Текст без удаленных абзацев
    """
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    
    # Удаляем абзацы в обратном порядке, чтобы индексы не сдвигались
    for para_num in sorted(paragraph_nums, reverse=True):
        if 1 <= para_num <= len(paragraphs):
            paragraphs.pop(para_num - 1)
    
    # Собираем обратно
    return '\n\n'.join(paragraphs)


def remove_paragraph_programmatically(text: str, paragraph_num: int) -> str:
    """
    Программно удаляет указанный абзац из текста
    
    Args:
        text: Исходный текст
        paragraph_num: Номер абзаца для удаления (1-based)
        
    Returns:
        Текст без удаленного абзаца
    """
    return remove_paragraphs_programmatically(text, [paragraph_num])

