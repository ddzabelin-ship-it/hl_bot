import asyncio
import logging
import pytz

from telegram import Bot
from telegram.error import TelegramError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ============ НАСТРОЙКИ (при желании можно изменить) ============
TOKEN = "8458423184:AAGRqzCZyysNc62oudYC8TX7CNMqraRKTW4"  # Ваш токен
CHAT_ID = -1003705629246  # ID вашего чата (группы)
TIMEZONE = "Europe/Moscow"  # Часовой пояс (например, Asia/Yekaterinburg)
SEND_HOUR = 15      # Час отправки (0-23)
SEND_MINUTE = 30    # Минута отправки
TEXT_TEMPLATE = "Прошу выполнить от 10 заданий № {} из РешуОГЭ(ЕГЭ) сегодня и прислать скриншот"
MAX_NUMBER = 16    # Максимальный номер задания (цикл от 1 до MAX_NUMBER)
# ================================================================

STATE_FILE = "counter.txt"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def read_counter():
    """Читает текущий номер задания из файла. Если файла нет - создаёт с 1."""
    try:
        with open(STATE_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        with open(STATE_FILE, "w") as f:
            f.write("1")
        return 1

def write_counter(value):
    """Записывает номер задания в файл."""
    with open(STATE_FILE, "w") as f:
        f.write(str(value))

async def send_daily_task():
    """Отправляет сообщение и обновляет счётчик."""
    bot = Bot(token=TOKEN)
    try:
        task_num = read_counter()
        message = TEXT_TEMPLATE.format(task_num)
        await bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info(f"Отправлено: {message}")

        # Увеличиваем номер, сбрасываем после MAX_NUMBER
        next_num = task_num + 1
        if next_num > MAX_NUMBER:
            next_num = 1
        write_counter(next_num)
        logger.info(f"Следующий номер: {next_num}")

    except TelegramError as e:
        logger.error(f"Ошибка отправки: {e}")
    except Exception as e:
        logger.error(f"Общая ошибка: {e}")

async def main():
    scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))
    scheduler.add_job(
        send_daily_task,
        trigger=CronTrigger(hour=SEND_HOUR, minute=SEND_MINUTE, timezone=pytz.timezone(TIMEZONE))
    )
    scheduler.start()
    logger.info(f"Бот запущен. Будет отправлять ежедневно в {SEND_HOUR:02d}:{SEND_MINUTE:02d} по времени {TIMEZONE}")

    # Бесконечное ожидание
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        scheduler.shutdown()
        logger.info("Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())