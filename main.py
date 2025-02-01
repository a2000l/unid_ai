from http import HTTPStatus
from dashscope import Application
import dashscope
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, Updater
import logging
import os
from threading import Thread
from flask import Flask, request
import asyncio



# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получение секретных данных из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY')
DASHSCOPE_APP_ID = os.getenv('DASHSCOPE_APP_ID')

# Проверяем наличие обязательных переменных окружения
if not TELEGRAM_BOT_TOKEN or not DASHSCOPE_API_KEY or not DASHSCOPE_APP_ID:
    raise ValueError("Не все необходимые переменные окружения установлены")

# Загрузка базы знаний из файла
with open('faq.json', 'r', encoding='utf-8') as f:
    faq_data = json.load(f)

# Настройка базового URL для DashScope
dashscope.base_http_api_url = 'https://dashscope-intl.aliyuncs.com/api/v1'

# Установка API ключа
dashscope.api_key = DASHSCOPE_API_KEY  # Вставьте ваш API ключ здесь


# Веб-сервер для поддержания активности
app = Flask(__name__)


@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.process_update(update)
    return '', 200



# Функция для получения ответа от Qwen API
def get_qwen_response(user_message, session_id=None):
    app_id = DASHSCOPE_APP_ID  # Вставьте ваш APP ID здесь
    if session_id:
        response = Application.call(app_id=app_id,
                                   prompt=user_message,
                                   session_id=session_id)
    else:
        response = Application.call(app_id=app_id,
                                   prompt=user_message)

    if response.status_code != HTTPStatus.OK:
        logging.error('request_id=%s, code=%s, message=%s\n' % (response.request_id, response.status_code, response.message))
        return "Произошла ошибка при обращении к API", None

    output = response.output.get('text', '') or ''
    next_session_id = response.output.get('session_id', None)
    return output, next_session_id

# Обработка команды /start
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Привет! Я бот ОО "Белорусский союз дизайнеров". Как я могу помочь?')

# Обработка текстовых сообщений
async def handle_message(update: Update, context: CallbackContext) -> None:
    user_message = update.message.text.lower()
    response = "Извините, я не понимаю ваш запрос. Пожалуйста, уточните вопрос."
    session_id = context.user_data.get('session_id', None)
    # Проверяем базу знаний (FAQ)
    for faq in faq_data['faq']:
        if user_message in faq['question'].lower():
            response = faq['answer']
            break
    else:
        # Если нет совпадения в FAQ, обращаемся к Qwen API
        response, new_session_id = get_qwen_response(user_message, session_id)
        if new_session_id:
            context.user_data['session_id'] = new_session_id
    await update.message.reply_text(response)


# Функция для обработки ошибок
async def error_handler(update: object, context: CallbackContext) -> None:
    logging.error(msg="Exception while handling an update:", exc_info=context.error)


# Глобальная переменная application
application = None



async def set_webhook():
    global application
    if application is None:
        raise ValueError("Application has not been initialized")

    render_url = os.getenv('RENDER_EXTERNAL_URL')
    if not render_url:
        logging.error("RENDER_EXTERNAL_URL environment variable is not set")
        raise ValueError("RENDER_EXTERNAL_URL is not set")

    url = f"https://{render_url}/webhook"
    if not url.startswith("https://"):
        logging.error("Webhook URL must start with 'https://'")
        raise ValueError("Webhook URL must start with 'https://'")

    try:
        # Удаление старого вебхука
        await application.bot.delete_webhook()
        # Установка нового вебхука
        await application.bot.set_webhook(url=url)
        logging.info(f"Webhook successfully set to {url}")
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")
        raise





def main():
    global application
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

# Запуск Flask в отдельном потоке
def run_flask():
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))

flask_thread = Thread(target=run_flask)
flask_thread.daemon = True  # Позволяет потоку завершаться вместе с основным процессом

if __name__ == '__main__':
    main()  # Инициализация application
    asyncio.run(set_webhook())  # Установка вебхука
    flask_thread.start()  # Запуск Flask сервера
