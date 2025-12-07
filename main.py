"""Главный файл запуска бота"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config.settings import settings
from services.telegram_service import TelegramService
from services import dependencies
from handlers import admin_handlers, employee_handlers, employee_admin_handlers, source_admin_handlers

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Основная функция запуска бота"""
    logger.info("Запуск бота...")
    
    # Инициализация бота и диспетчера
    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # Инициализация сервисов
    telegram_service = TelegramService(bot)
    dependencies.init_services(bot, telegram_service)
    
    # Регистрация обработчиков
    # Важно: FSM обработчики должны быть зарегистрированы ПЕРЕД общими обработчиками
    dp.include_router(employee_admin_handlers.router)  # FSM обработчики для админа
    dp.include_router(source_admin_handlers.router)  # FSM обработчики для источников
    dp.include_router(admin_handlers.router)
    dp.include_router(employee_handlers.router)  # Общие обработчики для сотрудников
    
    # Запуск планировщика
    if dependencies.scheduler_service:
        dependencies.scheduler_service.start()
    
    # Запуск периодической проверки таймаутов сотрудников
    async def check_employee_timeouts():
        while True:
            await asyncio.sleep(3600)  # Проверка каждый час
            if dependencies.employee_service:
                await dependencies.employee_service.check_timeouts()
    
    asyncio.create_task(check_employee_timeouts())
    
    try:
        logger.info("Бот запущен и готов к работе")
        await dp.start_polling(bot)
    finally:
        if dependencies.scheduler_service:
            dependencies.scheduler_service.stop()
        if dependencies.source_parser_service:
            await dependencies.source_parser_service.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

