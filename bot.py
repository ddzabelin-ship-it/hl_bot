import asyncio
import logging
from datetime import datetime
import pytz

from telegram import Bot
from telegram.error import TelegramError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ============ НАСТРОЙКИ (ЗАМЕНИТЕ НА СВОИ) ============
TOKEN = "7234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"  # токен от @BotFather
CHAT_ID = -1001234567890  # ID чата, куда отправлять
TIMEZONE = "Europe/Moscow"  # ваш часовой пояс (например Europe/Moscow, Asia/Almaty)
# =====================================================

# Файл для хранения текущего номера задания (будет создан автоматически)
STATE_FILE = "counter.txt"

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def read_counter():
    """Читает текущий номер задания из файла. Если файла нет - создаёт с 1."""
    try:
        with open(STATE_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        # Файл отсутствует или повреждён – начинаем с 1
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
        # Читаем текущий номер
        task_num = read_counter()
        message = f"Прошу выполнить задание № {task_num} сегодня"
        
        # Отправляем сообщение
        await bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info(f"Отправлено: {message}")
        
        # Увеличиваем номер, сбрасываем после 16
        next_num = task_num + 1
        if next_num > 16:
            next_num = 1
        write_counter(next_num)
        logger.info(f"Следующий номер: {next_num}")
        
    except TelegramError as e:
        logger.error(f"Ошибка отправки: {e}")
    except Exception as e:
        logger.error(f"Общая ошибка: {e}")

async def main():
    """Главная функция – запускает планировщик."""
    scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))
    
    # Планируем задачу на 09:00 каждый день
    scheduler.add_job(
        send_daily_task,
        trigger=CronTrigger(hour=9, minute=0, timezone=pytz.timezone(TIMEZONE))
    )
    
    scheduler.start()
    logger.info("Бот запущен и будет отправлять сообщения ежедневно в 09:00")
    
    # Держим скрипт активным
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        scheduler.shutdown()
        logger.info("Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())