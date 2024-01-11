import os
import re
import threading
import concurrent.futures
import requests
import datetime
import argparse

from google.cloud import firestore
import asyncio
import logging
import sqlite3
import json
from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler, CallbackContext
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

# Установка пути к файлу с ключами аутентификации
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'firebase.json'
# Инициализация клиента Firestore
db = firestore.Client()

# Включение логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def load_texts_from_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)


# ! STEP 1
async def step1(telegram_id, bot):

    media_group = [
        InputMediaPhoto(open(f'img/step2_{lang}.jpg', 'rb'))]
    # Отправляем группу изображений

    await bot.send_media_group(chat_id=telegram_id, media=media_group)

    # Текст с гиперссылками
    message_text = (
        texts[lang]["step2"]
    )

    button1 = InlineKeyboardButton(text=texts[lang]["join_club"], url="https://play.clubgg.net/dlink/EYt26hYpgX3fyrYZ6")

    # Создание разметки клавиатуры с кнопками
    keyboard = InlineKeyboardMarkup([[button1]])

    await bot.send_message(chat_id=telegram_id,
        text=message_text, 
        reply_markup=keyboard,
        parse_mode='HTML',
        disable_web_page_preview=True)



    button2 = InlineKeyboardButton(text=texts[lang]["next"], callback_data="to_send_player_id_step")
    # Создание разметки клавиатуры с кнопками
    keyboard2 = InlineKeyboardMarkup([[button2]])
    message_text2 = (
        texts[lang]["enter_club_id"]
    )

    await bot.send_message(chat_id=telegram_id,
        text=message_text2, 
        reply_markup=keyboard2,
        parse_mode='HTML',
        disable_web_page_preview=True)



def on_event(document_snapshot, changes, read_time, bot, loop):
    for change in changes:
        if change.type.name == 'ADDED':
            doc = change.document
            data = doc.to_dict()
            telegram_id = data['telegram_id']
            ctime = data['ctime']

            if data['type'] == 'join_group':
                # Планируем асинхронную операцию из другого потока
                db.collection('events').document(doc.id).delete()
                create_or_update_user(telegram_id, step='step1', join_group_time=ctime, conversion='join_group')

                loop.call_soon_threadsafe(
                    asyncio.create_task, 
                    step1(telegram_id, bot))


def get_click_id(key):
    base_url = "https://cointracker.ru/click?key="
    target_url = base_url + key

    # Отправляем запрос, не следуя за редиректами
    response = requests.get(target_url, allow_redirects=False)

    # Проверяем наличие заголовка Location для редиректа
    if 'Location' in response.headers:
        redirect_url = response.headers['Location']

        # Извлекаем click_ID из URL
        click_id = redirect_url.split('=')[-1]
        return click_id
    else:
        return None

def send_conversion(click_id,status):
    target_url = "https://cointracker.ru/click?cnv_id="+click_id+"&cnv_status="+status

    # Отправляем запрос на запись конверсии
    requests.get(target_url, allow_redirects=False)


def listen_to_events_sync(bot, loop):
    events_ref = db.collection('events')
    events_ref.on_snapshot(lambda doc_snapshot, changes, read_time: on_event(doc_snapshot, changes, read_time, bot, loop))


def create_or_update_user(telegram_id, step=None, click_id=None, join_group_time=None, conversion=None):
    users_ref = db.collection('users')
    user_ref = users_ref.document(str(telegram_id))
    print(f"Create user {telegram_id}")
    update_data = {}
    if step:
        update_data['step'] = step
    if click_id:
        update_data['click_id'] = click_id
    if join_group_time:
        update_data['join_group_time'] = join_group_time

    if update_data:
        users_ref = db.collection('users')
        user_doc = users_ref.document(str(telegram_id)).get()
        if not user_doc.exists:
            update_data['ctime'] = datetime.datetime.now()
            user_ref.create(update_data)   
        else:
            user_data = user_doc.to_dict()  # Преобразование DocumentSnapshot в словарь
            if 'click_id' in user_data and user_data['click_id'] is not None:
                print("USER CLICKID: " + user_data['click_id'])
                click_id = user_data['click_id']
            else:
                print("No clickID")
            user_ref.update(update_data)
            
    if click_id is not None and conversion is not None:
        send_conversion(click_id,conversion)
        
    return click_id

# ! STEP 0
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user

    click_id = None
    # Проверяем, есть ли аргументы с командой /start
    args = context.args
    if args:
        start_param = args[0]  # Первый аргумент после /start
        print(f"Received start parameter: {start_param}")
        if not start_param.startswith('clc') and len(start_param) > 19:
            click_id = get_click_id(start_param)
        if start_param.startswith('clc') and len(start_param) > 20:
            click_id = start_param[3:]
        # Теперь можно обработать start_param
    else:
        print("No start parameter received.")

    print(user.id)
    create_or_update_user(user.id, step='step0', click_id=click_id, conversion='start')

    # Создаем кнопку
    channel_button = InlineKeyboardButton(text=texts[lang]["subscribe"], url=texts[lang]["tg_channel"])

    # Создаем разметку клавиатуры и добавляем в нее нашу кнопку
    keyboard = InlineKeyboardMarkup([[channel_button]])


    media_group = [
        InputMediaPhoto(open(f'img/step1_{lang}.jpg', 'rb')),
    ]
    # Отправляем группу изображений
    await context.bot.send_media_group(chat_id=user.id, media=media_group)
    
    users_ref = db.collection('group_users')
    user_doc = users_ref.document(str(user.id)).get()
    if user_doc.exists:
        await context.bot.send_message(chat_id=user.id,
            text= texts[lang]["step1_skip"],
            # reply_markup=keyboard, 
            parse_mode='HTML')
        create_or_update_user(user.id, step='step1', conversion='join_group')
        await step1(user.id, context.bot)
        
    else:    
        await context.bot.send_message(chat_id=user.id,
            text= texts[lang]["step1"], 
            reply_markup=keyboard, 
            parse_mode='HTML')
    

        
    

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback function for inline keyboard."""
    query = update.callback_query
    await query.answer()
    if query.data == 'to_send_player_id_step':

        media_group = [
            InputMediaPhoto(open(f'img/acc_{lang}.jpg', 'rb')),
        ]
        # Отправляем группу изображений
        await context.bot.send_media_group(chat_id=update.effective_user.id, media=media_group)
        
        message_text2 = (
            texts[lang]["send_id"]
        )

        await context.bot.send_message(chat_id=update.effective_user.id,
            text=message_text2, 
            parse_mode='HTML',
            disable_web_page_preview=True)



async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await step1(update.effective_user.id, context.bot)
    # await context.bot.send_message(chat_id=-1002045841886, text="Hi")

async def process_account_id(user_id, number, bot):
    # Пользователь находится на step1, создаем запись в accounts
    accounts_ref = db.collection('accounts')
    account_id = f"gg{number}"
    accounts_ref.document(account_id).set({
        'ctime': firestore.SERVER_TIMESTAMP,
        'telegram_id': user_id
    })


    media_group = [
        InputMediaPhoto(open(f'img/step3_{lang}.jpg', 'rb')),
    ]
    # Отправляем группу изображений
    await bot.send_media_group(chat_id=user_id, media=media_group)

    # await bot.send_message(chat_id=user_id, text="Запись создана.")
    # Создаем кнопку
    channel_button = InlineKeyboardButton(text=texts[lang]["operator"], url=texts[lang]["operator_link"])

    # Создаем разметку клавиатуры и добавляем в нее нашу кнопку
    keyboard = InlineKeyboardMarkup([[channel_button]])

    await bot.send_message(chat_id=user_id,
        text=texts[lang]["step3"], 
        reply_markup=keyboard, 
        parse_mode='HTML')

    create_or_update_user(user_id, step='step3', conversion='player_id')

async def check_player_id_exists(player_id):
    users_ref = db.collection('accounts')
    user_doc = users_ref.document('gg'+str(player_id)).get()
    return user_doc.exists


# Получаем пользовательский ввод (например номера его player_id)
async def input_processing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    user_id = update.effective_user.id
    text = update.message.text

    users_ref = db.collection('users')
    user_doc = users_ref.document(str(user_id)).get()

    if user_doc.exists and user_doc.to_dict().get('step') == 'step1':
        # Проверка, является ли текст числом
        if re.match("^[0-9-]+$", text):
            if not await check_player_id_exists(text):
                await process_account_id(user_id, text, context.bot)
            else:
                await update.message.reply_text(texts[lang]["allready_reg"])
        else:
            await update.message.reply_text(texts[lang]["only_dig"])

    else:
        await update.message.reply_text(texts[lang]["wrong_input"])




def main():
    parser = argparse.ArgumentParser(description='Telegram Bot')
    parser.add_argument('--lang', type=str, choices=['ru', 'ua'], help='Language for the bot (ru/ua)', required=True)
    args = parser.parse_args()

    global lang
    global texts
    global main_loop
    
    # Использование языкового параметра
    lang = args.lang
    # Загрузка текстов в зависимости от выбранного языка
    texts = load_texts_from_json(f"dict/{lang}.json")
    config = load_texts_from_json(f"config.json")

    application = Application.builder().token(config[f"token_{lang}"]).build()
        
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, input_processing))

    bot = application.bot
    main_loop = asyncio.get_event_loop()

    # Запуск синхронного слушателя в отдельном потоке
    listener_thread = threading.Thread(target=listen_to_events_sync, args=(application.bot, main_loop))
    listener_thread.start()

    

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()