"""Сервис для управления промптами и их адаптации на основе обратной связи"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class PromptConfigService:
    """Сервис для управления промптами и их адаптации"""
    
    def __init__(self):
        self.config_file = Path("config/prompts.json")
        self.prompts: Dict = {}
        self._load_prompts()
    
    def _load_prompts(self):
        """Загружает промпты из файла"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.prompts = json.load(f)
                logger.info(f"Загружено {len(self.prompts)} промптов")
            else:
                logger.warning("Файл промптов не найден, используем дефолтные")
                self.prompts = {}
        except Exception as e:
            logger.error(f"Ошибка при загрузке промптов: {e}")
            self.prompts = {}
    
    def _save_prompts(self):
        """Сохраняет промпты в файл"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.prompts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении промптов: {e}")
    
    def get_prompt(self, prompt_key: str, prompt_type: str = "system_prompt") -> Optional[str]:
        """
        Получает промпт по ключу
        
        Args:
            prompt_key: Ключ промпта (например, "generate_post")
            prompt_type: Тип промпта ("system_prompt" или "user_prompt")
            
        Returns:
            Текст промпта или None
        """
        if prompt_key in self.prompts:
            prompt_data = self.prompts[prompt_key]
            return prompt_data.get(prompt_type)
        return None
    
    def get_prompt_info(self, prompt_key: str) -> Optional[Dict]:
        """
        Получает информацию о промпте
        
        Args:
            prompt_key: Ключ промпта
            
        Returns:
            Словарь с информацией о промпте или None
        """
        return self.prompts.get(prompt_key)
    
    def get_all_prompts(self) -> Dict:
        """Возвращает все промпты"""
        return self.prompts.copy()
    
    def set_prompt(self, prompt_key: str, prompt_type: str, prompt_text: str):
        """
        Устанавливает промпт
        
        Args:
            prompt_key: Ключ промпта
            prompt_type: Тип промпта ("system_prompt" или "user_prompt")
            prompt_text: Текст промпта
        """
        if prompt_key not in self.prompts:
            self.prompts[prompt_key] = {
                "name": prompt_key,
                "description": "",
                "system_prompt": "",
                "user_prompt": ""
            }
        
        self.prompts[prompt_key][prompt_type] = prompt_text
        self._save_prompts()
        logger.info(f"Промпт {prompt_key}.{prompt_type} обновлен")
    
    def adapt_prompt_based_on_feedback(
        self,
        prompt_key: str,
        post_history_service,
        min_success_rate: float = 0.7
    ) -> bool:
        """
        Адаптирует промпт на основе обратной связи из истории
        
        Args:
            prompt_key: Ключ промпта для адаптации
            post_history_service: Сервис истории постов
            min_success_rate: Минимальный процент успешных постов для адаптации (0.7 = 70%)
            
        Returns:
            True если промпт был адаптирован
        """
        if not post_history_service:
            return False
        
        # Получаем инсайты из истории
        insights = post_history_service.get_learning_insights()
        stats = insights.get("stats", {})
        recommendations = insights.get("recommendations", [])
        
        # Проверяем, нужна ли адаптация
        total_posts = stats.get("total_posts", 0)
        if total_posts < 10:  # Недостаточно данных для адаптации
            logger.info(f"Недостаточно данных для адаптации промпта {prompt_key}: {total_posts} постов")
            return False
        
        approved_posts = stats.get("approved_posts", 0)
        success_rate = approved_posts / total_posts if total_posts > 0 else 0
        
        if success_rate >= min_success_rate:
            logger.info(f"Успешность постов достаточна ({success_rate:.2%}), адаптация не требуется")
            return False
        
        # Получаем текущий промпт
        current_prompt = self.get_prompt(prompt_key, "system_prompt")
        if not current_prompt:
            logger.warning(f"Промпт {prompt_key} не найден")
            return False
        
        # Анализируем частые правки и адаптируем промпт
        common_edits = stats.get("common_edits", {})
        adapted_prompt = current_prompt
        
        # Адаптация на основе частых правок
        if common_edits.get("shorten", 0) > 10:
            # Часто требуется сокращение - добавляем инструкцию о краткости
            if "КОРОТКИМИ" not in adapted_prompt.upper():
                adapted_prompt += "\n\nВАЖНО: Генерируй максимально короткие посты. Избегай длинных предложений и лишних деталей."
        
        if common_edits.get("add_emoji", 0) > 10:
            # Часто требуется добавление эмодзи - усиливаем инструкцию
            if "эмодзи" in adapted_prompt.lower():
                # Усиливаем существующую инструкцию
                adapted_prompt = adapted_prompt.replace(
                    "Используй много эмодзи",
                    "ОБЯЗАТЕЛЬНО используй много эмодзи (минимум 1 эмодзи на каждые 2 предложения)"
                )
            else:
                adapted_prompt += "\n\nВАЖНО: Обязательно используй эмодзи для визуального оформления (минимум 1 эмодзи на каждые 2 предложения)."
        
        if common_edits.get("add_greeting", 0) > 5:
            # Часто требуется приветствие - добавляем инструкцию
            if "приветствие" not in adapted_prompt.lower():
                adapted_prompt += "\n\nВАЖНО: Начинай пост с дружелюбного приветствия (например, 'Добрый день!' или 'Привет!')."
        
        if common_edits.get("add_farewell", 0) > 5:
            # Часто требуется прощание - добавляем инструкцию
            if "прощание" not in adapted_prompt.lower():
                adapted_prompt += "\n\nВАЖНО: Заканчивай пост дружелюбным прощанием (например, 'Следите за обновлениями!' или 'Благодарим за внимание!')."
        
        # Применяем адаптацию только если промпт изменился
        if adapted_prompt != current_prompt:
            self.set_prompt(prompt_key, "system_prompt", adapted_prompt)
            logger.info(f"Промпт {prompt_key} адаптирован на основе обратной связи. Успешность: {success_rate:.2%}")
            return True
        
        return False
    
    def auto_adapt_prompts(self, post_history_service):
        """
        Автоматически адаптирует все промпты на основе обратной связи
        
        Args:
            post_history_service: Сервис истории постов
        """
        if not post_history_service:
            return
        
        adapted_count = 0
        for prompt_key in self.prompts.keys():
            if self.adapt_prompt_based_on_feedback(prompt_key, post_history_service):
                adapted_count += 1
        
        if adapted_count > 0:
            logger.info(f"Адаптировано {adapted_count} промптов на основе обратной связи")
