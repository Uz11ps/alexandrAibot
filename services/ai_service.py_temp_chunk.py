    async def generate_post_from_sources(self, source_posts: List[Dict[str, str]]) -> str:
        """
        Генерирует пост на основе анализа постов из других источников
        """
        if not source_posts:
            logger.warning("Нет постов из источников для анализа")
            return self._get_fallback_source_post()
        
        # Формируем текст для анализа из всех постов и список ссылок
        posts_text = []
        source_links = set()
        for i, post in enumerate(source_posts[:10], 1):
            source_type = post.get('source_type', 'unknown')
            text = post.get('text', '')
            link = post.get('source', '')
            if text:
                posts_text.append(f"Пост {i} ({source_type}):\n{text}\n")
            if link:
                source_links.add(link)
        
        sources_context = "\n---\n".join(posts_text)
        links_str = "\n".join([f"• {link}" for link in source_links])
        
        # Получаем системный промпт из конфигурации
        if self.prompt_config_service:
            system_prompt = self.prompt_config_service.get_prompt("generate_from_sources", "system_prompt")
        else:
            system_prompt = "Ты редактор Археон. Создай развернутый пост на основе источников."

        user_prompt = f"""Ниже приведены посты из внешних источников. 
Твоя задача: проанализировать их и создать ОДНУ самостоятельную, уникальную и экспертную новость для компании "Археон".

КРИТИЧЕСКИ ВАЖНО:
1. Текст должен быть РАЗВЕРНУТЫМ (1500-2000 символов). Не экономь на деталях.
2. В самом конце поста ОБЯЗАТЕЛЬНО добавь блок:
📌 **Источники для ознакомления:**
{links_str}

3. Если последний пост (Пост 1) ссылается на предыдущие события, обязательно найди контекст в предыдущих постах и сделай новость САМОСТОЯТЕЛЬНОЙ.
4. Читатель не должен догадываться, что это пересказ. Это должно звучать как авторская колонка Археон.
5. Соблюдай ГЕО-фильтр: Крым и Севастополь.

ИСТОЧНИКИ:
{sources_context}"""
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"Попытка {attempt + 1}: Генерация развернутого поста из {len(source_posts)} источников")
                
                # Формируем параметры запроса
                request_params = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_completion_tokens": 4000
                }
                
                if self.supports_temperature:
                    request_params["temperature"] = 0.7
                
                timeout = 180.0 if self.proxy_enabled else 60.0
                
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(**request_params),
                    timeout=timeout
                )
                
                result = response.choices[0].message.content.strip()
                
                # Очищаем ответ
                clean_text = clean_ai_response(result)
                
                # ПРИНУДИТЕЛЬНО добавляем источники, если их нет в тексте или они в самом конце
                if source_links and "Источники для ознакомления" not in clean_text:
                    clean_text += f"\n\n📌 <b>Источники для ознакомления:</b>\n{links_str}"
                
                return markdown_to_html(clean_text)
                
            except Exception as e:
                logger.error(f"Попытка {attempt + 1} не удалась: {e}")
                if attempt < max_retries - 1:
                    # Пробуем сменить прокси или ключ перед следующей попыткой
                    self._switch_proxy()
                    self._switch_api_key()
                    continue
                else:
                    break
                    
        return self._get_fallback_source_post()

