import asyncio
import logging
import pytz

from telegram import Bot, Poll
from telegram.error import TelegramError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ============ НАСТРОЙКИ ============
TOKEN = "8458423184:AAGRqzCZyysNc62oudYC8TX7CNMqraRKTW4"  # Ваш токен
CHAT_ID = -1003705629246  # ID вашего чата (группы)
TIMEZONE = "Europe/Moscow"  # Часовой пояс
SEND_HOUR = 15      # Час отправки
SEND_MINUTE = 40    # Минута отправки
TEXT_TEMPLATE = "Прошу выполнить от 10 заданий № {} из РешуОГЭ(ЕГЭ) сегодня и прислать скриншот"
MAX_NUMBER = 16     # Максимальный номер задания
# ===================================

STATE_FILE = "counter.txt"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def read_counter():
    try:
        with open(STATE_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        with open(STATE_FILE, "w") as f:
            f.write("1")
        return 1

def write_counter(value):
    with open(STATE_FILE, "w") as f:
        f.write(str(value))

async def send_daily_task():
    """Отправляет сообщение, затем опрос, и обновляет счётчик."""
    bot = Bot(token=TOKEN)
    try:
        task_num = read_counter()

        # 1. Отправляем текстовое напоминание
        message = TEXT_TEMPLATE.format(task_num)
        await bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info(f"Сообщение отправлено: {message}")

        # 2. Отправляем опрос о прогрессе
        question = f"Задание № {task_num}: твой прогресс?"
        options = ["Сделал", "В процессе", "Не успеваю сделать сегодня"]
        await bot.send_poll(
            chat_id=CHAT_ID,
            question=question,
            options=options,
            is_anonymous=False,          # все видят, кто ответил
            allows_multiple_answers=False,  # только один вариант
            type=Poll.REGULAR            # обычный опрос (не викторина)
        )
        logger.info(f"Опрос отправлен: {question}")

        # 3. Обновляем счётчик для следующего дня
        next_num = task_num + 1
        if next_num > MAX_NUMBER:
            next_num = 1
        write_counter(next_num)
        logger.info(f"Следующий номер: {next_num}")

    except TelegramError as e:
        logger.error(f"Ошибка Telegram: {e}")
    except Exception as e:
        logger.error(f"Общая ошибка: {e}")

async def main():
    scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))
    scheduler.add_job(
        send_daily_task,
        trigger=CronTrigger(hour=SEND_HOUR, minute=SEND_MINUTE, timezone=pytz.timezone(TIMEZONE))
    )
    scheduler.start()
    logger.info(f"✅ Бот запущен. Ежедневная отправка в {SEND_HOUR:02d}:{SEND_MINUTE:02d} {TIMEZONE}")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        scheduler.shutdown()
        logger.info("🛑 Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())