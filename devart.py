import requests
import random
from config import bot
import os
import logging
from dotenv import load_dotenv
load_dotenv()

# Настройки API DeviantArt
CLIENT_ID = os.getenv('DEVART_CLIENT_ID')
CLIENT_SECRET = os.getenv('DEVART_CLIENT_SECRET')
DEVIANTART_TOKEN_URL = 'https://www.deviantart.com/oauth2/token'
DEVIANTART_DEVIANTS_YOU_WATCH_URL = 'https://www.deviantart.com/api/v1/oauth2/browse/tags'
CHAT_ID = os.getenv("CHATID")  # замени на свой ID или юзернейм

def get_deviantart_access_token():
    """Получаем токен доступа для DeviantArt API"""
    response = requests.post(DEVIANTART_TOKEN_URL, data={
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    })
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        logging.error('Не удалось получить токен доступа')
        return None

def get_random_image(access_token):
    """Получаем случайное изображение от пользователей, на которых ты подписан в DeviantArt"""
    params = {
        'access_token': access_token,
        'tag': 'thighs',
        'mature_content': 'true'
    }
    response = requests.get(DEVIANTART_DEVIANTS_YOU_WATCH_URL, params=params)
    if response.status_code == 200:
        data = response.json()
        results = data.get('results', [])
        if results:
            random_image = random.choice(results)
            return {
                'url': random_image.get('url'),
                'title': random_image.get('title'),
                'image_url': random_image['content']['src']
            }
        else:
            logging.warning("Результаты отсутствуют в ответе")
    else:
        logging.error(f"Ошибка при запросе изображения: {response.status_code} - {response.text}")
    return None

def send_image_to_telegram(image_data):
    """Отправляем изображение в Telegram"""
    if image_data:
        bot.send_photo(CHAT_ID, photo=image_data['image_url'], caption=f"{image_data['title']}\n{image_data['url']}")
    else:
        logging.info("Нет данных для отправки")

def send_deviantart_image():
    """Получаем и отправляем изображение из DeviantArt в Telegram"""
    access_token = get_deviantart_access_token()
    if access_token:
        image_data = get_random_image(access_token)
        send_image_to_telegram(image_data)



# # Для запуска файла напрямую из терминала
# def send_image_to_telegram(image_data):
#     """Отправляем изображение в Telegram"""
#     if image_data:
#         bot.send_photo(CHAT_ID, photo=image_data['image_url'], caption=f"{image_data['title']}\n{image_data['url']}")
#     else:
#         print("Нет данных для отправки")

# # Run
# def main():
#     access_token = get_deviantart_access_token()
#     if access_token:
#         image_data = get_random_image(access_token)
#         send_image_to_telegram(image_data)

# if __name__ == '__main__':
#     main()