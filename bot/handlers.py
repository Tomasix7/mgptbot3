import logging
from config import client_groq, bot, request_queue
from bot.truncation_utils import truncate_messages  # Обрезка сообщений
from dialogue_storage import dialogue_storage
from characters import get_character
from bot.utils import is_authorized, notify_admin, DuplicateMessageFilter
import hashlib
import asyncio
import time
import os
from config import TTS_ENABLED_USERS
from tts import text_to_speech, remove_emoji
# from pymongo import MongoClient

# Глобальная переменная для хранения хеша последнего сообщения для фильтрации дублей
last_request_hash = None
# Создаем экземпляр фильтра
duplicate_filter = DuplicateMessageFilter()

# Обработчик команды /anima
@bot.message_handler(commands=['anima'])
def start_message(message):
    # Фильтрация дублирующего сообщения. Проверка на дубликат
    if duplicate_filter.is_duplicate(message.text):
        return  # Если сообщение дубликат, выходим из функции
    
    # Отправляем первое сообщение
    msg = bot.send_message(message.chat.id, "Пишу...")
    
    # Запускаем цикл анимации
    for i in range(1, 4):
        # Редактируем текст с добавлением точек
        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text="Пишу ✍️ " + "❤️"*i)
        time.sleep(5)  # Задержка на 1 секунду между изменениями
    
    # Финальное сообщение
    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text="Готово! 💖")

# TEST: Heart : animation ? 
@bot.message_handler(commands=['heart'])
def start_message(message):
    bot.send_message(message.chat.id, "❤️")


# TEST: POSITIVE RESPONSE
@bot.message_handler(commands=['start'])
def start_message(message):

    # Фильтрация дублирующего сообщения. Проверка на дубликат
    if duplicate_filter.is_duplicate(message.text):
        return  # Если сообщение дубликат, выходим из функции

    bot.send_message(message.chat.id, """
    Привет! 😊 
Я могу быть твоим ботфрендом 😎, говорить о чем угодно 😉 и присылать сообщения 💌 
    """)

@bot.message_handler(commands=['restart'])
def restart_model(message):
    if not is_authorized(message.chat.id):
        bot.send_message(message.chat.id, "Привет 😊 Пока у нас нет доступа друг к другу 😌")
        return

    # chat_id = str(message.chat.id) 1
    chat_id = message.chat.id
    try:
        result = dialogue_storage.collection.delete_many({'chat_id': chat_id})
        
        if result.deleted_count > 0:
            logging.info(f'Удалено {result.deleted_count} сообщений для чата {chat_id}')
            bot.send_message(message.from_user.id, f'Ок, давай начнем с чистого листа! 😊📝 Очищено {result.deleted_count} сообщений для чата № {chat_id}.')
        else:
            logging.info(f'Коллекция пуста для чата {chat_id}')
            bot.send_message(message.from_user.id, f'Коллекция уже пуста. Нечего удалять для чата № {chat_id}. 😄 Давай всё равно начнём заново.')
    except Exception as e:
        logging.error(f'Ошибка при обработке команды /restart: {e}')
        bot.send_message(message.from_user.id, 'Что-то пошло не так... 🫤')

@bot.message_handler(commands=['len'])
def get_dialogue_length(message):
    # Фильтрация дублирующего сообщения. Проверка на дубликат
    if duplicate_filter.is_duplicate(message.text):
        return  # Если сообщение дубликат, выходим из функции
    
    if not is_authorized(message.chat.id):
        bot.send_message(message.chat.id, "Привет 😊 Пока у нас нет доступа друг к другу 😌")
        return

    # chat_id = str(message.chat.id) 2
    chat_id = message.chat.id
    
    all_messages = dialogue_storage.get_messages(chat_id)
    total_chars = sum(len(msg['content']) for msg in all_messages)
    message_count = len(all_messages)
    
    response = f"Статистика диалога:\n\n"
    response += f"Количество сообщений: {message_count}\n\n"
    response += f"Общее количество символов: {total_chars}\n\n"
    response += f"Первое сообщение: {all_messages[0]['timestamp'] if all_messages else 'Нет сообщений'}\n\n"
    response += f"Последнее сообщение: {all_messages[-1]['timestamp'] if all_messages else 'Нет сообщений'}"
    
    bot.send_message(message.from_user.id, response)

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>     DBASE HANDLER     >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

  # Обработчик команды для введения нового пользователя. Перенесен в отдельный файл db_handler.py

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>     TOOLS FOR TOOL USE MODEL     >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# Define a tool for browsing the internet

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>     TEXT HANDLER     >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    ADMIN_CHAT_ID = os.getenv('CHATID')
    notify_admin(bot, message, ADMIN_CHAT_ID)

    if not is_authorized(message.chat.id):
        bot.send_message(message.chat.id, "Привет 😊 Пока у нас нет доступа друг к другу 😌")
        return

    global last_request_hash
    heart_message = bot.send_message(message.chat.id, "💚")
    current_hash = hashlib.md5(message.text.encode()).hexdigest()

    if current_hash == last_request_hash:
        bot.edit_message_text(chat_id=message.chat.id, message_id=heart_message.message_id, text="❤️")
        return
    
    last_request_hash = current_hash

    logging.debug(f'User chat_id: {message.chat.id}')
    logging.info(f'Received message: {message.text}')
    
    chat_id = message.chat.id
    dialogue_storage.add_message(chat_id, 'user', message.text)
    dialogue_history = dialogue_storage.get_messages(chat_id)
    max_messages = 10
    if len(dialogue_history) > max_messages:
        dialogue_history = dialogue_history[-max_messages:]

    messages_for_groq = truncate_messages([
        {"role": msg["role"], "content": msg["content"]} for msg in dialogue_history
    ])

    # character_info, character_name, users_gender, timezone = get_character(message.chat.id)
    character_info, character_name, users_gender, timezone, object_id = get_character(message.chat.id)
    system_message = {"role": "system", "content": character_info}
    messages = [system_message] + messages_for_groq

    async def send_request():
        try:
            response = client_groq.chat.completions.create(
                model='llama-3.3-70b-versatile', 
                messages=messages, temperature=0
            )
            model_response = response.choices[0].message.content
            bot.edit_message_text(chat_id=message.chat.id, message_id=heart_message.message_id, text=model_response)
            dialogue_storage.add_message(chat_id, 'assistant', model_response)

            # Отправка аудио
            voice_name = TTS_ENABLED_USERS.get(str(object_id), "en-US-AvaMultilingualNeural")
            text_to_speech(bot, model_response, chat_id, voice_name=voice_name)
        except Exception as e:
            logging.error(f'Error when sending request to Groq: {e}')
            bot.edit_message_text(chat_id=message.chat.id, message_id=heart_message.message_id, text="Отправь мне смайлик 🙏 🥰")

    asyncio.run(request_queue.add_request(send_request))