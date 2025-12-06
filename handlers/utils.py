"""Вспомогательные функции для обработчиков"""
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
import logging

logger = logging.getLogger(__name__)


async def safe_answer_callback(callback: CallbackQuery, text: str = "", show_alert: bool = False):
    """Безопасно отвечает на callback запрос"""
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        if "query is too old" in str(e) or "query ID is invalid" in str(e):
            logger.debug(f"Устаревший callback запрос: {callback.data}")
        else:
            logger.warning(f"Ошибка при ответе на callback: {e}")


async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасно редактирует сообщение"""
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        return True
    except TelegramBadRequest as e:
        if "query is too old" in str(e) or "query ID is invalid" in str(e):
            logger.debug(f"Устаревший callback запрос, отправляем новое сообщение: {callback.data}")
            # Отправляем новое сообщение вместо редактирования
            try:
                await callback.message.answer(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                return True
            except Exception as e2:
                logger.error(f"Ошибка при отправке нового сообщения: {e2}")
                return False
        elif "message is not modified" in str(e):
            logger.debug("Сообщение не изменено")
            return True
        else:
            logger.warning(f"Ошибка при редактировании сообщения: {e}")
            return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при редактировании сообщения: {e}")
        return False


async def safe_clear_state(state, callback: CallbackQuery = None):
    """Безопасно очищает состояние FSM"""
    try:
        await state.clear()
    except Exception as e:
        logger.warning(f"Ошибка при очистке состояния: {e}")
        # Пытаемся получить состояние и очистить его вручную
        try:
            current_state = await state.get_state()
            if current_state:
                await state.set_state(None)
        except:
            pass

