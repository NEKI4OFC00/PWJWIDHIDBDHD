import telebot
from telebot import types
import sqlite3
import random
import string
from datetime import datetime, timedelta
import threading
import os
import time
from concurrent.futures import ThreadPoolExecutor

# Замените на ваш токен бота
BOT_TOKEN = '7219521716:AAEt7ticEXm1cGNouNF7Kqjt544cpb0Bm4U'

# ID администраторов бота
ADMIN_IDS = [6665308361, 7168398511]
REPORT_ADMIN_ID = 6665308361  # ID администратора для получения жалоб

bot = telebot.TeleBot(BOT_TOKEN)

# Подключение к базе данных SQLite
conn = sqlite3.connect('referrals.db', check_same_thread=False, timeout=20)

# Создаем блокировку для безопасного доступа к базе данных
db_lock = threading.Lock()

# Инициализация таблиц в базе данных
with db_lock:
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            invited_count INTEGER DEFAULT 0,
            first_time BOOLEAN DEFAULT 1,
            username TEXT,
            registration_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            duration INTEGER,
            used BOOLEAN DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_promotions (
            user_id INTEGER PRIMARY KEY,
            end_time TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY,
            admin_id INTEGER,
            reason TEXT
        )
    ''')

# Глобальные переменные
user_report_time = {}
user_report_mode = {}

# Функции
def get_username(user_id):
    with db_lock:
        cursor = conn.cursor()
        cursor.execute('SELECT username FROM referrals WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
    return result[0] if result else None

def get_user_id(username):
    with db_lock:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM referrals WHERE username = ?', (username,))
        result = cursor.fetchone()
    return result[0] if result else None

def generate_promocode(prefix):
    code = prefix + ''.join(random.choice(string.ascii_uppercase) for _ in range(5))
    code += random.choice(string.digits + '#&!?')
    return code

def save_user_data():
    with db_lock:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user_promotions')
        users = cursor.fetchall()
    with open('user_data.txt', 'w') as f:
        for user in users:
            user_id, end_time = user
            f.write(f'{user_id},{end_time}\n')

def load_user_data():
    file_path = 'user_data.txt'
    if os.path.exists(file_path):
        with db_lock:
            cursor = conn.cursor()
            with open(file_path, 'r') as f:
                for line in f:
                    user_id, end_time = line.strip().split(',')
                    cursor.execute('INSERT OR REPLACE INTO user_promotions (user_id, end_time) VALUES (?, ?)', (user_id, end_time))
            conn.commit()
    else:
        print(f"File {file_path} does not exist")

def schedule_updates():
    threading.Timer(1800, schedule_updates).start()
    save_user_data()

def is_user_banned(user_id):
    with db_lock:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM banned_users WHERE user_id = ?', (user_id,))
        return cursor.fetchone() is not None

def generate_main_menu_markup(user_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("Купить подписку", callback_data="buy_subscription"),
        types.InlineKeyboardButton("Рефералка", callback_data="referral")
    )
    
    if user_id in ADMIN_IDS:
        markup.row(types.InlineKeyboardButton("Создать промокод", callback_data="create_promocode"))

    with db_lock:
        cursor = conn.cursor()
        cursor.execute('SELECT end_time FROM user_promotions WHERE user_id = ?', (user_id,))
        promotion = cursor.fetchone()
    if not promotion or datetime.strptime(promotion[0], '%Y-%m-%d %H:%M:%S.%f') <= datetime.now():
        markup.row(types.InlineKeyboardButton("Промокод", callback_data="promocode"))
    
    if promotion and datetime.strptime(promotion[0], '%Y-%m-%d %H:%M:%S.%f') > datetime.now():
        markup.row(types.InlineKeyboardButton("Снос", callback_data="snos"))

    markup.row(types.InlineKeyboardButton("Оставшееся время", callback_data="remaining_time"))

    return markup

# Обработчики команд
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)

    if is_user_banned(user_id):
        with db_lock:
            cursor = conn.cursor()
            cursor.execute('SELECT admin_id, reason FROM banned_users WHERE user_id = ?', (user_id,))
            admin_id, reason = cursor.fetchone()
        admin_username = get_username(admin_id) or f"@{admin_id}"
        bot.send_message(message.chat.id, f"Вы были заблокированы в данном боте администратором {admin_username} по причине {reason}\n"
                                          f"Если вы считаете данный бан ошибочным, напишите администратору.")
        return

    with db_lock:
        cursor = conn.cursor()
        cursor.execute('SELECT first_time FROM referrals WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()

        if not result:
            referrer_id = message.text.split("?start=")[-1] if '?start=' in message.text else None
            cursor.execute('INSERT INTO referrals (user_id, referrer_id, invited_count, first_time, username) VALUES (?, ?, 1, 1, ?)', (user_id, referrer_id, username))
        else:
            referrer_id = None

        cursor.execute('UPDATE referrals SET first_time = 0, username = ? WHERE user_id = ?', (username, user_id))
        conn.commit()

    referral_link = f"https://t.me/{bot.get_me().username}?start={user_id}"

    with db_lock:
        cursor = conn.cursor()
        cursor.execute('SELECT invited_count FROM referrals WHERE user_id = ?', (user_id,))
        invited_count = cursor.fetchone()[0]

    markup = generate_main_menu_markup(user_id)

    bot.send_message(message.chat.id, 
        "Добро пожаловать в MIDEROV SNOS!\n\n"
        "С помощью нашего бота вы сможете отправлять большое количество жалоб на пользователей и их каналы\n"
        "Приобретите подписку по кнопке ниже!",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    user_id = call.from_user.id

    if is_user_banned(user_id):
        with db_lock:
            cursor = conn.cursor()
            cursor.execute('SELECT admin_id, reason FROM banned_users WHERE user_id = ?', (user_id,))
            admin_id, reason = cursor.fetchone()
        admin_username = get_username(admin_id) or f"@{admin_id}"
        bot.send_message(call.message.chat.id, f"Вы были заблокированы в данном боте администратором {admin_username} по причине {reason}\n"
                                              f"Если вы считаете данный бан ошибочным, напишите администратору.")
        return

    if call.data == "buy_subscription":
        bot.answer_callback_query(call.id, text="Выберите продолжительность подписки:")

        price_text = ("Прайс данного бота💸\n1 день - 50₽\n1 неделя - 150₽\n1 месяц - 400₽\n1 год - 1000₽\nнавсегда - 3500₽\n Писать по поводу покупки📥 - @liderdoxa\n"
                      "Так же, если вы хотите приобрести сразу много ключей условно под раздачу, то возможен опт🔥"
                     )

        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("Назад", callback_data="main_menu"))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=price_text,
            reply_markup=markup
        )

    elif call.data == "referral":
        referral_link = f"https://t.me/{bot.get_me().username}?start={call.from_user.id}"

        with db_lock:
            cursor = conn.cursor()
            cursor.execute('SELECT invited_count FROM referrals WHERE user_id = ?', (call.from_user.id,))
            result = cursor.fetchone()
            invited_count = result[0] if result else 0

        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("Назад", callback_data="main_menu"))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Приглашая по данной ссылке пользователей в бота, вы будете получать 20% времени с купленной ими подписки.\n\n"
                 f"Ваша ссылка: {referral_link}\n\n"
                 f"Количество приглашенных: {invited_count}",
            reply_markup=markup
        )

    elif call.data == "create_promocode":
        if user_id in ADMIN_IDS:
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("2 часа", callback_data="create_promocode_0.0833"),
                types.InlineKeyboardButton("1 день", callback_data="create_promocode_1"),
                types.InlineKeyboardButton("1 неделя", callback_data="create_promocode_7"),
                types.InlineKeyboardButton("1 месяц", callback_data="create_promocode_30")
            )
            markup.row(
                types.InlineKeyboardButton("1 год", callback_data="create_promocode_365"),
                types.InlineKeyboardButton("Навсегда", callback_data="create_promocode_forever")
            )
            markup.row(types.InlineKeyboardButton("Назад", callback_data="main_menu"))

            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Выберите продолжительность промокода:",
                reply_markup=markup
            )
        else:
            bot.answer_callback_query(call.id, text="У вас нет прав для выполнения этой команды")

    elif call.data.startswith("create_promocode_"):
        if user_id in ADMIN_IDS:
            duration = call.data.split("_")[2]
            if duration == "forever":
                prefix = "FOREVER-"
                duration_text = "навсегда"
            else:
                duration = float(duration)
                if duration == 0.0833:
                    prefix = "2H-"
                    duration_text = "2 часа"
                elif duration == 1:
                    prefix = "1D-"
                    duration_text = "1 день"
                elif duration == 7:
                    prefix = "1W-"
                    duration_text = "1 неделя"
                elif duration == 30:
                    prefix = "1M-"
                    duration_text = "1 месяц"
                elif duration == 365:
                    prefix = "1Y-"
                    duration_text = "1 год"
                else:
                    prefix = ""
                    duration_text = f"{duration} дней"

            code = generate_promocode(prefix)

            with db_lock:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO promocodes (code, duration) VALUES (?, ?)', (code, duration))
                conn.commit()

            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("Назад", callback_data="main_menu"))

            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"Создан промокод: `{code}`\nПродолжительность: {duration_text}",
                parse_mode='Markdown',
                reply_markup=markup
            )
        else:
            bot.answer_callback_query(call.id, text="У вас нет прав для выполнения этой команды")

    elif call.data == "promocode":
        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("Назад", callback_data="main_menu"))

        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите промокод:",
            reply_markup=markup
        )
        
        bot.register_next_step_handler(msg, process_promocode)

    elif call.data == "snos":
        with db_lock:
            cursor = conn.cursor()
            cursor.execute('SELECT end_time FROM user_promotions WHERE user_id = ?', (user_id,))
            promotion = cursor.fetchone()
        
        if promotion and datetime.strptime(promotion[0], '%Y-%m-%d %H:%M:%S.%f') > datetime.now():
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("Назад", callback_data="main_menu"))

            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите текст жалобы✍️:",
                reply_markup=markup
            )

            user_report_mode[user_id] = True
            bot.register_next_step_handler(msg, process_report)
        else:
            bot.answer_callback_query(call.id, text="У вас нет активной подписки")

    elif call.data == "remaining_time":
        with db_lock:
            cursor = conn.cursor()
            cursor.execute('SELECT end_time FROM user_promotions WHERE user_id = ?', (user_id,))
            promotion = cursor.fetchone()

        if promotion:
            end_time = datetime.strptime(promotion[0], '%Y-%m-%d %H:%M:%S.%f')
            remaining_time = end_time - datetime.now()
            days, seconds = remaining_time.days, remaining_time.seconds
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60

            remaining_time_text = f"Оставшееся время подписки: {days} дней, {hours} часов и {minutes} минут"
        else:
            remaining_time_text = "У вас нет активной подписки"

        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("Назад", callback_data="main_menu"))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=remaining_time_text,
            reply_markup=markup
        )

    elif call.data == "main_menu":
        markup = generate_main_menu_markup(user_id)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Вы вернулись в главное меню",
            reply_markup=markup
        )

def process_promocode(message):
    user_id = message.from_user.id
    code = message.text.strip().upper()

    with db_lock:
        cursor = conn.cursor()
        cursor.execute('SELECT duration, used FROM promocodes WHERE code = ?', (code,))
        promocode = cursor.fetchone()

    if promocode:
        duration, used = promocode
        if used:
            bot.send_message(message.chat.id, "Этот промокод уже использован")
        else:
            if duration == "forever":
                end_time = datetime.max
            else:
                end_time = datetime.now() + timedelta(days=float(duration))
            with db_lock:
                cursor = conn.cursor()
                cursor.execute('INSERT OR REPLACE INTO user_promotions (user_id, end_time) VALUES (?, ?)', (user_id, end_time))
                cursor.execute('UPDATE promocodes SET used = 1 WHERE code = ?', (code,))
                conn.commit()

            bot.send_message(message.chat.id, f"Промокод успешно активирован! Ваша подписка активна до {end_time}")

            admin_username = get_username(REPORT_ADMIN_ID) or f"@{REPORT_ADMIN_ID}"
            user_username = get_username(user_id) or f"@{user_id}"
            admin_who_created = get_username(ADMIN_IDS[0]) or f"@{ADMIN_IDS[0]}"
            bot.send_message(REPORT_ADMIN_ID, 
                f"Пользователь {user_username} активировал промокод *{code}* на {duration} дней✅\n"
                f"Промокод создан администратором: {admin_who_created} ℹ️",
                parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, "Неверный промокод")

    markup = generate_main_menu_markup(user_id)
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

def process_report(message):
    user_id = message.from_user.id

    if not user_report_mode.get(user_id, False):
        markup = generate_main_menu_markup(user_id)
        bot.send_message(message.chat.id, "Вы вернулись в главное меню", reply_markup=markup)
        return

    if is_user_banned(user_id):
        with db_lock:
            cursor = conn.cursor()
            cursor.execute('SELECT admin_id, reason FROM banned_users WHERE user_id = ?', (user_id,))
            admin_id, reason = cursor.fetchone()
        admin_username = get_username(admin_id) or f"@{admin_id}"
        bot.send_message(message.chat.id, f"Вы были заблокированы в данном боте администратором {admin_username} по причине {reason}\n"
                                          f"Если вы считаете данный бан ошибочным, напишите администратору.")
        user_report_mode[user_id] = False
        return

    report_target = message.text.strip()
    current_time = datetime.now()

    if user_id in user_report_time and (current_time - user_report_time[user_id]).total_seconds() < 600:
        bot.send_message(message.chat.id, "Вы можете отправлять жалобы не чаще, чем раз в 10 минут")
        user_report_mode[user_id] = False
        return

    user_report_time[user_id] = current_time

    user_username = get_username(user_id) or f"@{user_id}"
    bot.send_message(REPORT_ADMIN_ID, f"Пользователь {user_username} отправил жалобу: {report_target}")
    bot.send_message(message.chat.id, "Ваш запрос принят, ожидайте сноса✅")

    user_report_mode[user_id] = False

    markup = generate_main_menu_markup(user_id)
    bot.send_message(message.chat.id, "Вы вернулись в главное меню", reply_markup=markup)

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if message.from_user.id in ADMIN_IDS:
        try:
            command, user_identifier, *reason = message.text.split()
            reason = " ".join(reason) if reason else "Не указана"

            if user_identifier.startswith('@'):
                user_id = get_user_id(user_identifier[1:])
            else:
                user_id = int(user_identifier)

            if user_id:
                with db_lock:
                    cursor = conn.cursor()
                    cursor.execute('INSERT INTO banned_users (user_id, admin_id, reason) VALUES (?, ?, ?)', (user_id, message.from_user.id, reason))
                    conn.commit()

                bot.send_message(message.chat.id, f"Пользователь {user_identifier} заблокирован")
            else:
                bot.send_message(message.chat.id, "Пользователь не найден")
        except ValueError:
            bot.send_message(message.chat.id, "Неверный формат команды. Используйте /ban <user_id или @username> <reason>")
    else:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if message.from_user.id in ADMIN_IDS:
        try:
            command, user_identifier = message.text.split()

            if user_identifier.startswith('@'):
                user_id = get_user_id(user_identifier[1:])
            else:
                user_id = int(user_identifier)

            if user_id:
                with db_lock:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
                    conn.commit()

                bot.send_message(message.chat.id, f"Пользователь {user_identifier} разблокирован")
            else:
                bot.send_message(message.chat.id, "Пользователь не найден")
        except ValueError:
            bot.send_message(message.chat.id, "Неверный формат команды. Используйте /unban <user_id или @username>")
    else:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды")

@bot.message_handler(commands=['status'])
def user_status(message):
    if message.from_user.id in ADMIN_IDS:
        try:
            command, user_identifier = message.text.split()

            if user_identifier.startswith('@'):
                user_id = get_user_id(user_identifier[1:])
                username = user_identifier
            else:
                user_id = int(user_identifier)
                username = get_username(user_id) or f"@{user_id}"

            if user_id:
                with db_lock:
                    cursor = conn.cursor()
                    cursor.execute('SELECT end_time FROM user_promotions WHERE user_id = ?', (user_id,))
                    promotion = cursor.fetchone()

                    cursor.execute('SELECT registration_time FROM referrals WHERE user_id = ?', (user_id,))
                    registration_time = cursor.fetchone()

                if promotion:
                    end_time = datetime.strptime(promotion[0], '%Y-%m-%d %H:%M:%S.%f')
                    remaining_time = end_time - datetime.now()
                    days, seconds = remaining_time.days, remaining_time.seconds
                    hours = seconds // 3600
                    minutes = (seconds % 3600) // 60
                    remaining_time_text = f"{days}дней {hours} часов {minutes} минут"
                else:
                    remaining_time_text = "Нету"

                if registration_time:
                    reg_time = datetime.strptime(registration_time[0], '%Y-%m-%d %H:%M:%S.%f')
                    time_since_registration = datetime.now() - reg_time
                    days = time_since_registration.days
                    hours, remainder = divmod(time_since_registration.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    time_since_registration_text = f"{days} дней {hours} часов {minutes} минут"
                else:
                    time_since_registration_text = "Неизвестно"

                status_message = (
                    f"Пользователь {username}\n"
                    f"Оставшееся время подписки🔥 {remaining_time_text}\n"
                    f"Время с момента регистрации: {time_since_registration_text}"
                )
                bot.send_message(message.chat.id, status_message)
            else:
                bot.send_message(message.chat.id, "Пользователь не найден")
        except ValueError:
            bot.send_message(message.chat.id, "Неверный формат команды. Используйте /status <user_id или @username>")
    else:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды")

@bot.message_handler(commands=['unsubscribe'])
def unsubscribe_user(message):
    if message.from_user.id in ADMIN_IDS:
        try:
            _, user_identifier, *reason = message.text.split()
            reason = " ".join(reason) if reason else "Причина не указана"

            if user_identifier.startswith('@'):
                user_id = get_user_id(user_identifier[1:])
            else:
                user_id = int(user_identifier)

            if user_id:
                with db_lock:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM user_promotions WHERE user_id = ?', (user_id,))
                    conn.commit()

                admin_username = get_username(message.from_user.id) or f"@{message.from_user.id}"
                bot.send_message(user_id, 
                    f"Администратор {admin_username} снял вам подписку по причине: *{reason}*.\n"
                    "Если вы не согласны с решением, то напишите администратору, что вам снял её.",
                    parse_mode='Markdown')

                bot.send_message(message.chat.id, f"Подписка пользователя {user_identifier} успешно отменена")
            else:
                bot.send_message(message.chat.id, "Пользователь не найден")
        except ValueError:
            bot.send_message(message.chat.id, "Неверный формат команды. Используйте /unsubscribe <user_id или @username> <причина>")
    else:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    
    if user_id not in user_report_mode or not user_report_mode[user_id]:
        markup = generate_main_menu_markup(user_id)
        bot.send_message(message.chat.id, "Вы вернулись в главное меню", reply_markup=markup)

def run_bot():
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"Bot encountered an error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    load_user_data()
    schedule_updates()
    executor = ThreadPoolExecutor(max_workers=10)
    executor.submit(run_bot)