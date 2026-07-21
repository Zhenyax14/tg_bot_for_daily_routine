import os

import schedule
from telegram import Bot
import random
import asyncio
from datetime import datetime, time

# Telegram bot token and chat ID
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')  # Use your actual bot token
CHAT_ID = os.getenv('CHAT_ID')  # Use your actual chat ID
THREAD_ID = os.getenv('THREAD_ID')  # Use your actual thread ID
value = 0



if TELEGRAM_BOT_TOKEN is None:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set.")

if CHAT_ID is None:
    raise ValueError("CHAT_ID environment variable is not set.")

if THREAD_ID is None:
    raise ValueError("THREAD_ID environment variable is not set.")


# Create a bot instance
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Function to send a notification message via Telegram


async def notify(message):
    try:
        print(f"Attempting to send message: {message}")
        await bot.send_message(chat_id=CHAT_ID, text=message, message_thread_id=THREAD_ID)
        # print(f'Successfully sent message: {message}')
    except Exception as e:
        print(f'Failed to send message: {e}')

# Loop function that updates the global value


def loop():
    global value
    for _ in range(100):
        value += random.randint(-2, 5)
        print(f"loop function - {value}")
    return value

# Main function to setup scheduling and run tasks


async def main():
    await notify("Инициализируюсь...")


    # Function to schedule notifications using asyncio.create_task
    def schedule_notifications():
        # Schedule tasks with proper handling
        schedule.every().day.at("07:00").do(lambda: asyncio.create_task(notify("От имени моего создателя желаю вам доброго утро, друзья")))
        schedule.every().day.at("07:15").do(lambda: asyncio.create_task(notify("Шанс игры @Duhastikx")))
        schedule.every().day.at("22:00").do(lambda: asyncio.create_task(notify("Спокойной ночи, друзья")))
        schedule.every(1800).seconds.do(lambda: asyncio.create_task(notify('@sql_excel Выпейте 100мл воды 💧')))
        schedule.every(2).hours.do(lambda: asyncio.create_task(notify('@Nikitaslav_Dobrosmysl @sql_excel 10 отжиманий 💪🏼')))

    # Schedule notifications
    schedule_notifications()

    # Running the scheduled tasks in an async loop
    while True:
        current_time = datetime.now().time()

        # Define the start and end time for the restricted range
        start_restricted_time = time(22, 00, 1)
        end_restricted_time = time(6, 59, 59)

        # Check if the current time is outside the restricted range
        if not (start_restricted_time <= current_time <= end_restricted_time):
            schedule.run_pending()


        await asyncio.sleep(1)  # Async sleep to avoid blocking the event loop

if __name__ == '__main__':
    asyncio.run(main())
