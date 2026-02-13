import telebot
from telebot import types
import os
from dotenv import load_dotenv
from database import Database
from current_api import (
    convert_currency, 
    get_exchange_rate, 
    get_currency_by_country,
    API_KEY
)
import re
from typing import Optional

# Загрузка переменных окружения
load_dotenv()

# Инициализация бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

bot = telebot.TeleBot(BOT_TOKEN)
db = Database()

# Состояния FSM
class UserState:
    WAITING_FROM_COUNTRY = "waiting_from_country"
    WAITING_TO_COUNTRY = "waiting_to_country"
    WAITING_MANUAL_RATE = "waiting_manual_rate"
    WAITING_INITIAL_AMOUNT = "waiting_initial_amount"
    WAITING_EXPENSE_CONFIRMATION = "waiting_expense_confirmation"


def get_main_menu_text(user_id: int) -> str:
    """Создает текст главного меню с информацией об активном путешествии"""
    trip = db.get_active_trip(user_id)
    
    text = "👋 Travel Wallet\n\n"
    
    if trip:
        # Получаем общую сумму расходов
        total_from, total_to = db.get_total_expenses(trip["id"])
        
        text += (
            f"📍 {trip['from_country']} ({trip['from_currency']}) → {trip['to_country']} ({trip['to_currency']})\n\n"
            f"💸 Потрачено: {total_to:,.2f} {trip['to_currency']} = {total_from:,.2f} {trip['from_currency']}\n\n"
            f"💰 Остаток: {trip['balance_to']:,.2f} {trip['to_currency']} = {trip['balance_from']:,.2f} {trip['from_currency']}\n\n"
            f"💡 Введите сумму расхода в валюте {trip['to_currency']}"
        )
    else:
        text += "У вас нет активного путешествия.\nСоздайте новое путешествие!\n\n"
        text += "Выберите действие:"
    
    return text


def get_main_menu_keyboard():
    """Создает главное меню с inline-кнопками"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(types.InlineKeyboardButton("✈️ Создать новое путешествие", callback_data="new_trip"))
    keyboard.add(types.InlineKeyboardButton("📋 Мои путешествия", callback_data="my_trips"))
    keyboard.add(types.InlineKeyboardButton("💰 Баланс", callback_data="balance"))
    keyboard.add(types.InlineKeyboardButton("📊 История расходов", callback_data="history"))
    keyboard.add(types.InlineKeyboardButton("💱 Изменить курс", callback_data="set_rate"))
    return keyboard


def show_main_menu(chat_id: int, user_id: int, message_id: int = None, edit: bool = False):
    """Показывает или обновляет главное меню"""
    text = get_main_menu_text(user_id)
    keyboard = get_main_menu_keyboard()
    
    if edit and message_id:
        try:
            msg = bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard
            )
            if msg:
                db.save_menu_message_id(user_id, msg.message_id)
        except Exception as e:
            # Если не удалось отредактировать, отправляем новое
            msg = bot.send_message(chat_id, text, reply_markup=keyboard)
            db.save_menu_message_id(user_id, msg.message_id)
    else:
        msg = bot.send_message(chat_id, text, reply_markup=keyboard)
        db.save_menu_message_id(user_id, msg.message_id)


def format_balance(trip: dict) -> str:
    """Форматирует баланс для отображения"""
    balance_from = trip["balance_from"]
    balance_to = trip["balance_to"]
    from_curr = trip["from_currency"]
    to_curr = trip["to_currency"]
    
    return f"💰 Остаток: {balance_to:,.2f} {to_curr} = {balance_from:,.2f} {from_curr}"


@bot.message_handler(commands=['start'])
def start_command(message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    
    # Очищаем состояние пользователя
    db.set_user_state(user_id, None)
    
    # Показываем главное меню с информацией об активном путешествии
    show_main_menu(message.chat.id, user_id)


@bot.callback_query_handler(func=lambda call: call.data == "new_trip")
def new_trip_callback(call):
    """Обработчик создания нового путешествия"""
    user_id = call.from_user.id
    
    # Разрешаем создавать несколько путешествий
    db.set_user_state(user_id, UserState.WAITING_FROM_COUNTRY)
    
    # Убираем меню и запрашиваем страну отправления
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="✈️ Создание нового путешествия\n\nВведите страну отправления (например: Россия, USA, Китай):"
    )


@bot.message_handler(commands=['newtrip'])
def new_trip_command(message):
    """Команда /newtrip"""
    user_id = message.from_user.id
    
    # Разрешаем создавать несколько путешествий
    db.set_user_state(user_id, UserState.WAITING_FROM_COUNTRY)
    bot.send_message(
        message.chat.id,
        "✈️ Создание нового путешествия\n\n"
        "Введите страну отправления (например: Россия, USA, Китай):"
    )


@bot.message_handler(func=lambda m: db.get_user_state(m.from_user.id) and 
                     db.get_user_state(m.from_user.id)[0] == UserState.WAITING_FROM_COUNTRY)
def handle_from_country(message):
    """Обработка ввода страны отправления"""
    user_id = message.from_user.id
    from_country = message.text.strip()
    
    from_currency = get_currency_by_country(from_country)
    if not from_currency:
        bot.send_message(
            message.chat.id,
            f"❌ Не удалось определить валюту для страны '{from_country}'.\n"
            "Пожалуйста, введите название страны еще раз (например: Россия, USA, Китай):"
        )
        return
    
    # Сохраняем данные во временном хранилище
    db.set_user_state(user_id, UserState.WAITING_TO_COUNTRY, 
                     f"{from_country}|{from_currency}")
    
    bot.send_message(
        message.chat.id,
        f"✅ Страна отправления: {from_country} ({from_currency})\n\n"
        "Теперь введите страну назначения:"
    )


@bot.message_handler(func=lambda m: db.get_user_state(m.from_user.id) and 
                     db.get_user_state(m.from_user.id)[0] == UserState.WAITING_TO_COUNTRY)
def handle_to_country(message):
    """Обработка ввода страны назначения"""
    user_id = message.from_user.id
    to_country = message.text.strip()
    
    to_currency = get_currency_by_country(to_country)
    if not to_currency:
        bot.send_message(
            message.chat.id,
            f"❌ Не удалось определить валюту для страны '{to_country}'.\n"
            "Пожалуйста, введите название страны еще раз:"
        )
        return
    
    # Получаем сохраненные данные
    state_data = db.get_user_state(user_id)[1]
    from_country, from_currency = state_data.split("|")
    
    if from_currency == to_currency:
        bot.send_message(
            message.chat.id,
            "❌ Валюты стран отправления и назначения совпадают!\n"
            "Пожалуйста, выберите разные страны."
        )
        return
    
    # Получаем курс обмена через API и сразу переходим к запросу суммы
    bot.send_message(message.chat.id, "⏳ Получаю курс обмена через API...")
    
    rate = get_exchange_rate(from_currency, to_currency)
    
    if rate is None:
        bot.send_message(
            message.chat.id,
            "❌ Не удалось получить курс обмена через API.\n"
            "Пожалуйста, введите курс вручную (например: 0.0125 для 1 CNY = 0.0125 RUB):"
        )
        db.set_user_state(user_id, UserState.WAITING_MANUAL_RATE,
                         f"{from_country}|{from_currency}|{to_country}|{to_currency}")
        return
    
    # Сохраняем курс и сразу запрашиваем начальную сумму
    db.set_user_state(user_id, UserState.WAITING_INITIAL_AMOUNT,
                     f"{from_country}|{from_currency}|{to_country}|{to_currency}|{rate}")
    
    bot.send_message(
        message.chat.id,
        f"✅ Страна назначения: {to_country} ({to_currency})\n"
        f"💱 Курс: 1 {from_currency} = {rate:.6f} {to_currency}\n\n"
        f"Введите начальную сумму в валюте {from_currency} (вашей домашней валюте):"
    )


# Убраны обработчики подтверждения курса - теперь курс берется автоматически из API


@bot.message_handler(func=lambda m: db.get_user_state(m.from_user.id) and 
                     db.get_user_state(m.from_user.id)[0] == UserState.WAITING_MANUAL_RATE)
def handle_manual_rate(message):
    """Обработка ввода курса вручную"""
    user_id = message.from_user.id
    
    try:
        rate = float(message.text.strip().replace(",", "."))
        if rate <= 0:
            raise ValueError("Курс должен быть положительным числом")
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ Неверный формат курса. Введите положительное число (например: 0.08):"
        )
        return
    
    state_data = db.get_user_state(user_id)[1]
    from_country, from_currency, to_country, to_currency = state_data.split("|")
    
    db.set_user_state(user_id, UserState.WAITING_INITIAL_AMOUNT,
                     f"{from_country}|{from_currency}|{to_country}|{to_currency}|{rate}")
    
    bot.send_message(
        message.chat.id,
        f"✅ Курс установлен: 1 {from_currency} = {rate:.6f} {to_currency}\n\n"
        f"Введите начальную сумму в валюте {from_currency} (вашей домашней валюте):"
    )


@bot.message_handler(func=lambda m: db.get_user_state(m.from_user.id) and 
                     db.get_user_state(m.from_user.id)[0] == UserState.WAITING_INITIAL_AMOUNT)
def handle_initial_amount(message):
    """Обработка ввода начальной суммы"""
    user_id = message.from_user.id
    
    try:
        amount = float(message.text.strip().replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ Неверный формат суммы. Введите положительное число:"
        )
        return
    
    state_data = db.get_user_state(user_id)[1]
    from_country, from_currency, to_country, to_currency, rate = state_data.split("|")
    rate = float(rate)
    
    # Конвертируем через API для точности
    bot.send_message(message.chat.id, "⏳ Конвертирую сумму через API...")
    
    conversion_data = convert_currency(amount, from_currency, to_currency)
    
    # Используем установленный пользователем курс
    actual_rate = rate
    
    if conversion_data:
        # Проверяем разные возможные структуры ответа API
        converted_amount = None
        
        # Попробуем найти результат в разных местах ответа
        if "info" in conversion_data:
            info = conversion_data["info"]
            if "quote" in info:
                # quote - это курс для 1 единицы, нужно умножить на сумму
                quote_value = float(info["quote"])
                converted_amount = amount * quote_value
            elif "rate" in info:
                # Если есть курс, вычисляем результат
                rate_value = float(info["rate"])
                converted_amount = amount * rate_value
        
        if converted_amount is None and "result" in conversion_data:
            # result обычно содержит результат конвертации для всей суммы
            result_value = float(conversion_data["result"])
            # Проверяем: если результат слишком большой, это может быть курс
            if result_value > amount * 1000:
                converted_amount = amount * result_value
            else:
                converted_amount = result_value
        
        if converted_amount is None and "query" in conversion_data:
            query = conversion_data["query"]
            if "result" in query:
                result_value = float(query["result"])
                if result_value > amount * 1000:
                    converted_amount = amount * result_value
                else:
                    converted_amount = result_value
        
        if converted_amount is None:
            # Если структура не распознана, используем введенный курс
            converted_amount = amount * rate
    else:
        # Если API не сработал, используем введенный курс
        converted_amount = amount * rate
    
    trip_id = db.create_trip(
        user_id=user_id,
        from_country=from_country,
        to_country=to_country,
        from_currency=from_currency,
        to_currency=to_currency,
        rate=actual_rate,
        initial_amount=amount
    )
    
    if trip_id:
        db.set_user_state(user_id, None)
        
        # Всегда показываем главное меню после создания путешествия
        # Сначала показываем меню, потом сообщение о создании
        show_main_menu(message.chat.id, user_id)
        
        # Отправляем сообщение о создании путешествия
        bot.send_message(
            message.chat.id,
            f"✅ Путешествие создано!\n\n"
            f"📍 {from_country} ({from_currency}) → {to_country} ({to_currency})\n"
            f"💰 Начальный баланс: {amount:,.2f} {from_currency} = {converted_amount:,.2f} {to_currency}"
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка при создании путешествия. Возможно, такое путешествие уже существует."
        )


def show_my_trips(user_id: int, chat_id: int, message_id: int = None, is_callback: bool = True):
    """Показывает список путешествий пользователя (общая функция)"""
    trips = db.get_user_trips(user_id)
    
    if not trips:
        if is_callback:
            return False
        else:
            return None
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    for trip in trips:
        # Создаем строку кнопок для каждого путешествия
        row_buttons = []
        
        # Кнопка переключения (если неактивно) или просмотра (если активно)
        if trip["is_active"]:
            row_buttons.append(types.InlineKeyboardButton(
                f"👁 {trip['from_country']} → {trip['to_country']}",
                callback_data=f"view_trip|{trip['id']}"
            ))
        else:
            row_buttons.append(types.InlineKeyboardButton(
                f"🔄 {trip['from_country']} → {trip['to_country']}",
                callback_data=f"switch_trip|{trip['id']}"
            ))
        
        # Кнопка удаления
        row_buttons.append(types.InlineKeyboardButton(
            "🗑",
            callback_data=f"delete_trip|{trip['id']}"
        ))
        
        keyboard.add(*row_buttons)
    
    keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
    
    text = "📋 Ваши путешествия:\n\n"
    text += "👁 - просмотр активного\n"
    text += "🔄 - активировать\n"
    text += "🗑 - удалить\n\n"
    text += "Выберите действие:"
    
    return keyboard, text


@bot.callback_query_handler(func=lambda call: call.data == "my_trips")
def my_trips_callback(call):
    """Показывает список путешествий пользователя"""
    user_id = call.from_user.id
    trips = db.get_user_trips(user_id)
    
    if not trips:
        bot.answer_callback_query(call.id, "У вас пока нет путешествий")
        show_main_menu(call.message.chat.id, user_id)
        return
    
    keyboard, text = show_my_trips(user_id, call.message.chat.id, call.message.message_id)
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("switch_trip|"))
def switch_trip_callback(call):
    """Переключает активное путешествие"""
    user_id = call.from_user.id
    trip_id = int(call.data.split("|")[1])
    
    if db.switch_trip(user_id, trip_id):
        trip = db.get_active_trip(user_id)
        bot.answer_callback_query(call.id, "✅ Путешествие активировано!")
        
        text = (
            f"✅ Активное путешествие:\n\n"
            f"📍 Из: {trip['from_country']} ({trip['from_currency']})\n"
            f"📍 В: {trip['to_country']} ({trip['to_currency']})\n"
            f"💱 Курс: 1 {trip['from_currency']} = {trip['rate']:.6f} {trip['to_currency']}\n\n"
            f"{format_balance(trip)}"
        )
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard
        )
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка при переключении", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("view_trip|"))
def view_trip_callback(call):
    """Просмотр активного путешествия"""
    user_id = call.from_user.id
    trip_id = int(call.data.split("|")[1])
    
    trips = db.get_user_trips(user_id)
    trip = next((t for t in trips if t["id"] == trip_id), None)
    
    if not trip:
        bot.answer_callback_query(call.id, "Путешествие не найдено", show_alert=True)
        return
    
    text = (
        f"✅ Активное путешествие:\n\n"
        f"📍 Из: {trip['from_country']} ({trip['from_currency']})\n"
        f"📍 В: {trip['to_country']} ({trip['to_currency']})\n"
        f"💱 Курс: 1 {trip['from_currency']} = {trip['rate']:.6f} {trip['to_currency']}\n\n"
        f"{format_balance(trip)}"
    )
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="my_trips"))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_trip|"))
def delete_trip_callback(call):
    """Обработчик удаления путешествия"""
    user_id = call.from_user.id
    trip_id = int(call.data.split("|")[1])
    
    # Получаем информацию о путешествии
    trips = db.get_user_trips(user_id)
    trip = next((t for t in trips if t["id"] == trip_id), None)
    
    if not trip:
        bot.answer_callback_query(call.id, "Путешествие не найдено", show_alert=True)
        return
    
    # Показываем подтверждение удаления
    text = (
        f"⚠️ Подтвердите удаление путешествия:\n\n"
        f"📍 Из: {trip['from_country']} ({trip['from_currency']})\n"
        f"📍 В: {trip['to_country']} ({trip['to_currency']})\n"
        f"💰 Баланс: {trip['balance_to']:.2f} {trip['to_currency']} = {trip['balance_from']:.2f} {trip['from_currency']}\n\n"
        f"Это действие нельзя отменить!"
    )
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete|{trip_id}"))
    keyboard.add(types.InlineKeyboardButton("❌ Отмена", callback_data="my_trips"))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete|"))
def confirm_delete_callback(call):
    """Подтверждение удаления путешествия"""
    user_id = call.from_user.id
    trip_id = int(call.data.split("|")[1])
    
    if db.delete_trip(user_id, trip_id):
        bot.answer_callback_query(call.id, "✅ Путешествие удалено")
        
        # Возвращаемся к списку путешествий
        trips = db.get_user_trips(user_id)
        
        if not trips:
            show_main_menu(call.message.chat.id, user_id, call.message.message_id, edit=True)
        else:
            # Показываем обновленный список используя общую функцию
            keyboard, text = show_my_trips(user_id, call.message.chat.id, call.message.message_id)
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=keyboard
            )
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка при удалении", show_alert=True)


@bot.message_handler(commands=['switch'])
def switch_command(message):
    """Команда /switch"""
    user_id = message.from_user.id
    trips = db.get_user_trips(user_id)
    
    if not trips:
        show_main_menu(message.chat.id, user_id)
        return
    
    keyboard, text = show_my_trips(user_id, message.chat.id, is_callback=False)
    
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data == "balance")
def balance_callback(call):
    """Показывает баланс активного путешествия"""
    user_id = call.from_user.id
    trip = db.get_active_trip(user_id)
    
    if not trip:
        bot.answer_callback_query(call.id, "У вас нет активного путешествия")
        bot.send_message(
            call.message.chat.id,
            "❌ У вас нет активного путешествия. Создайте новое!",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    text = (
        f"💰 Баланс путешествия:\n\n"
        f"📍 Из: {trip['from_country']} ({trip['from_currency']})\n"
        f"📍 В: {trip['to_country']} ({trip['to_currency']})\n"
        f"💱 Курс: 1 {trip['from_currency']} = {trip['rate']:.6f} {trip['to_currency']}\n\n"
        f"{format_balance(trip)}"
    )
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=keyboard
    )


@bot.message_handler(commands=['balance'])
def balance_command(message):
    """Команда /balance"""
    user_id = message.from_user.id
    trip = db.get_active_trip(user_id)
    
    if not trip:
        show_main_menu(message.chat.id, user_id)
        return
    
    text = (
        f"💰 Баланс путешествия:\n\n"
        f"📍 Из: {trip['from_country']} ({trip['from_currency']})\n"
        f"📍 В: {trip['to_country']} ({trip['to_currency']})\n"
        f"💱 Курс: 1 {trip['from_currency']} = {trip['rate']:.6f} {trip['to_currency']}\n\n"
        f"{format_balance(trip)}"
    )
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
    
    bot.send_message(message.chat.id, text, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data == "history")
def history_callback(call):
    """Показывает историю расходов"""
    user_id = call.from_user.id
    trip = db.get_active_trip(user_id)
    
    if not trip:
        bot.answer_callback_query(call.id, "У вас нет активного путешествия")
        bot.send_message(
            call.message.chat.id,
            "❌ У вас нет активного путешествия. Создайте новое!",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    expenses = db.get_expenses(trip["id"], limit=20)
    
    if not expenses:
        text = "📊 История расходов пуста.\n\nВы еще не совершили ни одного расхода."
    else:
        text = f"📊 История расходов (последние {len(expenses)}):\n\n"
        total_from = 0.0
        total_to = 0.0
        
        for exp in expenses:
            timestamp = exp["timestamp"].split()[0] if exp["timestamp"] else "N/A"
            # Используем точные значения из базы данных
            amount_to = float(exp["amount_to"])
            amount_from = float(exp["amount_from"])
            
            text += (
                f"📅 {timestamp}\n"
                f"   {amount_to:.2f} {trip['to_currency']} = "
                f"{amount_from:.2f} {trip['from_currency']}\n\n"
            )
            # Суммируем с точными значениями
            total_from += amount_from
            total_to += amount_to
        
        text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💸 Всего потрачено:\n"
            f"{total_to:.2f} {trip['to_currency']} = {total_from:.2f} {trip['from_currency']}"
        )
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=keyboard
    )


@bot.message_handler(commands=['history'])
def history_command(message):
    """Команда /history"""
    user_id = message.from_user.id
    trip = db.get_active_trip(user_id)
    
    if not trip:
        show_main_menu(message.chat.id, user_id)
        return
    
    expenses = db.get_expenses(trip["id"], limit=20)
    
    if not expenses:
        text = "📊 История расходов пуста.\n\nВы еще не совершили ни одного расхода."
    else:
        text = f"📊 История расходов (последние {len(expenses)}):\n\n"
        total_from = 0.0
        total_to = 0.0
        
        for exp in expenses:
            timestamp = exp["timestamp"].split()[0] if exp["timestamp"] else "N/A"
            # Используем точные значения из базы данных
            amount_to = float(exp["amount_to"])
            amount_from = float(exp["amount_from"])
            
            text += (
                f"📅 {timestamp}\n"
                f"   {amount_to:.2f} {trip['to_currency']} = "
                f"{amount_from:.2f} {trip['from_currency']}\n\n"
            )
            # Суммируем с точными значениями
            total_from += amount_from
            total_to += amount_to
        
        text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💸 Всего потрачено:\n"
            f"{total_to:.2f} {trip['to_currency']} = {total_from:.2f} {trip['from_currency']}"
        )
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
    
    bot.send_message(message.chat.id, text, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data == "set_rate")
def set_rate_callback(call):
    """Запрос на изменение курса"""
    user_id = call.from_user.id
    trip = db.get_active_trip(user_id)
    
    if not trip:
        bot.answer_callback_query(call.id, "У вас нет активного путешествия")
        bot.send_message(
            call.message.chat.id,
            "❌ У вас нет активного путешествия. Создайте новое!",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    db.set_user_state(user_id, "waiting_new_rate", str(trip["id"]))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            f"💱 Изменение курса обмена\n\n"
            f"Текущий курс: 1 {trip['from_currency']} = {trip['rate']:.6f} {trip['to_currency']}\n\n"
            f"Введите новый курс (сколько {trip['to_currency']} за 1 {trip['from_currency']}):"
        )
    )


@bot.message_handler(func=lambda m: db.get_user_state(m.from_user.id) and 
                     db.get_user_state(m.from_user.id)[0] == "waiting_new_rate")
def handle_new_rate(message):
    """Обработка нового курса"""
    user_id = message.from_user.id
    
    try:
        new_rate = float(message.text.strip().replace(",", "."))
        if new_rate <= 0:
            raise ValueError("Курс должен быть положительным")
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ Неверный формат курса. Введите положительное число:"
        )
        return
    
    trip_id = int(db.get_user_state(user_id)[1])
    
    if db.update_trip_rate(trip_id, new_rate):
        trip = db.get_active_trip(user_id)
        db.set_user_state(user_id, None)
        
        # Обновляем главное меню
        menu_message_id = db.get_menu_message_id(user_id)
        if menu_message_id:
            show_main_menu(message.chat.id, user_id, menu_message_id, edit=True)
        
        bot.send_message(
            message.chat.id,
            f"✅ Курс обновлен!\n\n"
            f"Новый курс: 1 {trip['from_currency']} = {new_rate:.6f} {trip['to_currency']}\n\n"
            f"{format_balance(trip)}"
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка при обновлении курса"
        )


@bot.message_handler(commands=['setrate'])
def setrate_command(message):
    """Команда /setrate"""
    user_id = message.from_user.id
    trip = db.get_active_trip(user_id)
    
    if not trip:
        show_main_menu(message.chat.id, user_id)
        return
    
    db.set_user_state(user_id, "waiting_new_rate", str(trip["id"]))
    
    bot.send_message(
        message.chat.id,
        f"💱 Изменение курса обмена\n\n"
        f"Текущий курс: 1 {trip['from_currency']} = {trip['rate']:.6f} {trip['to_currency']}\n\n"
        f"Введите новый курс (сколько {trip['to_currency']} за 1 {trip['from_currency']}):"
    )


@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu_callback(call):
    """Возврат в главное меню"""
    user_id = call.from_user.id
    show_main_menu(call.message.chat.id, user_id, call.message.message_id, edit=True)


# Обработка чисел как расходов
# Этот обработчик должен быть последним, чтобы не перехватывать команды
def handle_expense(message):
    """Обработка сообщений с числами как расходов"""
    # Пропускаем команды - они обрабатываются отдельными обработчиками
    if not message.text or message.text.startswith('/'):
        return
    
    user_id = message.from_user.id
    
    # Проверяем, не находится ли пользователь в процессе создания путешествия
    state = db.get_user_state(user_id)
    if state and state[0] not in [None, UserState.WAITING_EXPENSE_CONFIRMATION]:
        return  # Пропускаем, если пользователь в процессе создания путешествия
    
    # Получаем активное путешествие
    trip = db.get_active_trip(user_id)
    if not trip:
        # Если нет активного путешествия, показываем меню
        show_main_menu(message.chat.id, user_id)
        return
    
    # Пытаемся извлечь число из сообщения
    text = message.text.strip().replace(",", ".").replace(" ", "")
    
    # Ищем число в тексте
    numbers = re.findall(r'\d+\.?\d*', text)
    if not numbers:
        return  # Не число, игнорируем
    
    try:
        amount_to = float(numbers[0])
        if amount_to <= 0:
            return
    except ValueError:
        return
    
    # Конвертируем через API
    # amount_to - сумма в валюте страны пребывания (to_currency)
    # Нужно конвертировать в домашнюю валюту (from_currency)
    # rate хранится как: сколько to_currency за 1 from_currency
    # Значит для конвертации: amount_from = amount_to / rate
    
    conversion_data = convert_currency(amount_to, trip["to_currency"], trip["from_currency"])
    
    
    if conversion_data:
        # Проверяем разные возможные структуры ответа API
        amount_from = None
        
        if "info" in conversion_data:
            info = conversion_data["info"]
            if "quote" in info:
                # quote в API exchangerate.host - это курс для 1 единицы from_currency к to_currency
                # Но мы конвертируем из to_currency в from_currency (обратное направление)
                # API вызывается как: convert_currency(amount_to, to_currency, from_currency)
                # То есть конвертируем amount_to единиц to_currency в from_currency
                # API возвращает quote - курс для 1 единицы to_currency к from_currency
                # Значит: amount_from = amount_to * quote
                quote_value = float(info["quote"])
                amount_from = amount_to * quote_value
            elif "rate" in info:
                # Если есть курс, умножаем на сумму
                rate_value = float(info["rate"])
                amount_from = amount_to * rate_value
        
        if amount_from is None and "result" in conversion_data:
            # result обычно содержит результат конвертации
            result_value = float(conversion_data["result"])
            # Проверяем размер: если результат намного больше суммы, возможно это курс
            if result_value > amount_to * 100:
                # Скорее всего это курс, умножаем
                amount_from = amount_to * result_value
            else:
                amount_from = result_value
        
        if amount_from is None and "query" in conversion_data:
            query = conversion_data["query"]
            if "result" in query:
                result_value = float(query["result"])
                if result_value > amount_to * 100:
                    amount_from = amount_to * result_value
                else:
                    amount_from = result_value
        
        if amount_from is None:
            # Если структура не распознана, используем сохраненный курс
            # rate: сколько to_currency за 1 from_currency
            # Значит: amount_from = amount_to / rate
            amount_from = amount_to / trip["rate"]
    else:
        # Если API не сработал, используем сохраненный курс
        # rate: сколько to_currency за 1 from_currency
        # Значит: amount_from = amount_to / rate
        amount_from = amount_to / trip["rate"]
    
    # Сохраняем данные для подтверждения, включая message_id исходного сообщения
    db.set_user_state(user_id, UserState.WAITING_EXPENSE_CONFIRMATION,
                     f"{trip['id']}|{amount_to}|{amount_from}|{message.message_id}")
    
    # Показываем конвертацию и кнопки подтверждения
    # Отправляем временное сообщение с подтверждением
    text = (
        f"💸 Расход: {amount_to:.2f} {trip['to_currency']} = {amount_from:.2f} {trip['from_currency']}\n\n"
        f"Учесть как расход?"
    )
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("✅ Да", callback_data="expense_yes"))
    keyboard.add(types.InlineKeyboardButton("❌ Нет", callback_data="expense_no"))
    
    # Отправляем временное сообщение (оно будет удалено после подтверждения)
    bot.send_message(message.chat.id, text, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data == "expense_yes")
def expense_yes_callback(call):
    """Подтверждение расхода"""
    user_id = call.from_user.id
    state = db.get_user_state(user_id)
    
    if not state or state[0] != UserState.WAITING_EXPENSE_CONFIRMATION:
        bot.answer_callback_query(call.id, "Ошибка: состояние не найдено")
        return
    
    # Получаем путешествие сначала
    trip = db.get_active_trip(user_id)
    if not trip:
        bot.answer_callback_query(call.id, "Путешествие не найдено", show_alert=True)
        return
    
    state_parts = state[1].split("|")
    trip_id = int(state_parts[0])
    amount_to = float(state_parts[1])
    amount_from = float(state_parts[2])
    user_message_id = int(state_parts[3]) if len(state_parts) > 3 else None
    
    
    # Проверяем баланс
    if trip["balance_to"] < amount_to:
        bot.answer_callback_query(call.id, "Недостаточно средств!", show_alert=True)
        return
    
    # Добавляем расход
    if db.add_expense(trip_id, amount_to, amount_from):
        db.set_user_state(user_id, None)
        
        # Удаляем сообщение пользователя с числом
        if user_message_id:
            try:
                bot.delete_message(call.message.chat.id, user_message_id)
            except Exception:
                pass
        
        # Удаляем сообщение с подтверждением расхода
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        
        # Возвращаемся в главное меню с обновленной информацией
        menu_message_id = db.get_menu_message_id(user_id)
        if menu_message_id:
            try:
                # Редактируем существующее меню
                show_main_menu(call.message.chat.id, user_id, menu_message_id, edit=True)
                bot.answer_callback_query(call.id, f"✅ Расход учтен: {amount_to:.2f} {trip['to_currency']}")
            except Exception as e:
                # Если не удалось обновить меню, создаем новое
                show_main_menu(call.message.chat.id, user_id)
                bot.answer_callback_query(call.id, f"✅ Расход учтен: {amount_to:.2f} {trip['to_currency']}")
        else:
            # Если меню не найдено, создаем новое
            show_main_menu(call.message.chat.id, user_id)
            bot.answer_callback_query(call.id, f"✅ Расход учтен: {amount_to:.2f} {trip['to_currency']}")
    else:
        bot.answer_callback_query(call.id, "Ошибка при добавлении расхода", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data == "expense_no")
def expense_no_callback(call):
    """Отмена расхода"""
    user_id = call.from_user.id
    state = db.get_user_state(user_id)
    
    # Получаем message_id сообщения пользователя из состояния
    user_message_id = None
    if state and state[0] == UserState.WAITING_EXPENSE_CONFIRMATION:
        state_parts = state[1].split("|")
        if len(state_parts) > 3:
            try:
                user_message_id = int(state_parts[3])
            except:
                pass
    
    db.set_user_state(user_id, None)
    
    # Удаляем сообщение пользователя с числом
    if user_message_id:
        try:
            bot.delete_message(call.message.chat.id, user_message_id)
        except Exception:
            pass
    
    # Удаляем сообщение с подтверждением и возвращаемся в меню
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    
    # Возвращаемся в главное меню
    menu_message_id = db.get_menu_message_id(user_id)
    if menu_message_id:
        try:
            show_main_menu(call.message.chat.id, user_id, menu_message_id, edit=True)
        except:
            show_main_menu(call.message.chat.id, user_id)
    else:
        show_main_menu(call.message.chat.id, user_id)
    
    bot.answer_callback_query(call.id, "❌ Расход не учтен")


# Регистрируем обработчик расходов (должен быть последним, после всех команд)
# Используем условие, чтобы не перехватывать команды
@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'))
def handle_expense_wrapper(message):
    """Обертка для обработки расходов"""
    handle_expense(message)


if __name__ == "__main__":
    print("=" * 50)
    print("Запуск бота Travel Wallet...")
    print(f"Токен бота: {'✅ Установлен' if BOT_TOKEN else '❌ НЕ НАЙДЕН!'}")
    if BOT_TOKEN:
        print(f"Первые 10 символов токена: {BOT_TOKEN[:10]}...")
    
    # Проверяем информацию о боте
    try:
        bot_info = bot.get_me()
        print(f"Бот подключен: @{bot_info.username} ({bot_info.first_name})")
    except Exception as e:
        print(f"❌ Ошибка при получении информации о боте: {e}")
        print("Проверьте правильность токена в файле .env")
        exit(1)
    
    print("Ожидание сообщений...")
    print("=" * 50)
    
    try:
        # Удаляем старые вебхуки если есть
        bot.delete_webhook()
        print("Вебхуки удалены")
        
        # Запускаем polling
        print("Запуск polling...")
        bot.polling(none_stop=True, interval=0, timeout=20)
    except KeyboardInterrupt:
        print("\nБот остановлен пользователем")
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
        import traceback
        traceback.print_exc()
