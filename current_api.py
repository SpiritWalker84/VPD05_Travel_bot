import os
from dotenv import load_dotenv
import requests

# Загрузка переменных окружения
load_dotenv()

# Получение токенов из переменных окружения
API_KEY = os.getenv("CURRENCY_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")


def get_current_rate(default: str = "USD", currencies: list[str] = ["EUR", "GBP", "JPY"]):
    """
    Получает текущие курсы валют относительно базовой валюты.
    
    Args:
        default: Базовая валюта (по умолчанию USD)
        currencies: Список валют для получения курсов
    
    Returns:
        dict: Данные с курсами валют
    """
    url = "https://api.exchangerate.host/live"
    params = {
        "access_key": API_KEY,
        "source": default,
        "currencies": ",".join(currencies)
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе курсов валют: {e}")
        return None


def convert_currency(amount: float, from_currency: str, to_currency: str):
    """
    Конвертирует сумму из одной валюты в другую.
    
    Args:
        amount: Сумма для конвертации
        from_currency: Исходная валюта
        to_currency: Целевая валюта
    
    Returns:
        dict: Данные с результатом конвертации или None при ошибке
    """
    url = "https://api.exchangerate.host/convert"
    params = {
        "access_key": API_KEY,
        "from": from_currency,
        "to": to_currency,
        "amount": amount
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        
        # Проверяем успешность запроса
        if not data.get("success", False):
            error_info = data.get('error', {})
            if isinstance(error_info, dict):
                print(f"API вернул ошибку: {error_info.get('info', 'Unknown error')}")
            else:
                print(f"API вернул ошибку: {error_info}")
            return None
        
        return data
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при конвертации валюты: {e}")
        return None


def get_exchange_rate(from_currency: str, to_currency: str) -> Optional[float]:
    """
    Получает курс обмена между двумя валютами.
    
    Args:
        from_currency: Исходная валюта
        to_currency: Целевая валюта
    
    Returns:
        float: Курс обмена (сколько to_currency за 1 from_currency) или None при ошибке
    """
    # Конвертируем 1 единицу для получения курса
    data = convert_currency(1.0, from_currency, to_currency)
    
    if data:
        # Проверяем разные возможные структуры ответа
        if "info" in data and "quote" in data["info"]:
            return float(data["info"]["quote"])
        elif "result" in data:
            return float(data["result"])
        elif "query" in data and "result" in data:
            return float(data["query"]["result"])
    
    return None


# Маппинг стран к валютам (основные страны)
COUNTRY_TO_CURRENCY = {
    "Россия": "RUB", "Russia": "RUB", "RU": "RUB",
    "США": "USD", "USA": "USD", "United States": "USD", "US": "USD",
    "Евросоюз": "EUR", "EU": "EUR", "Europe": "EUR",
    "Германия": "EUR", "Germany": "EUR", "DE": "EUR",
    "Франция": "EUR", "France": "EUR", "FR": "EUR",
    "Великобритания": "GBP", "UK": "GBP", "United Kingdom": "GBP", "GB": "GBP",
    "Китай": "CNY", "China": "CNY", "CN": "CNY",
    "Япония": "JPY", "Japan": "JPY", "JP": "JPY",
    "Канада": "CAD", "Canada": "CAD", "CA": "CAD",
    "Австралия": "AUD", "Australia": "AUD", "AU": "AUD",
    "Швейцария": "CHF", "Switzerland": "CHF", "CH": "CHF",
    "Турция": "TRY", "Turkey": "TRY", "TR": "TRY",
    "Индия": "INR", "India": "INR", "IN": "INR",
    "Бразилия": "BRL", "Brazil": "BRL", "BR": "BRL",
    "Мексика": "MXN", "Mexico": "MXN", "MX": "MXN",
    "Южная Корея": "KRW", "South Korea": "KRW", "KR": "KRW",
    "Сингапур": "SGD", "Singapore": "SGD", "SG": "SGD",
    "Таиланд": "THB", "Thailand": "THB", "TH": "THB",
    "ОАЭ": "AED", "UAE": "AED", "United Arab Emirates": "AED", "AE": "AED",
    "Саудовская Аравия": "SAR", "Saudi Arabia": "SAR", "SA": "SAR",
}


def get_currency_by_country(country: str) -> Optional[str]:
    """
    Получает код валюты по названию страны.
    
    Args:
        country: Название страны (на русском или английском)
    
    Returns:
        str: Код валюты (ISO 4217) или None если не найдено
    """
    country_normalized = country.strip()
    
    # Проверяем точное совпадение
    if country_normalized in COUNTRY_TO_CURRENCY:
        return COUNTRY_TO_CURRENCY[country_normalized]
    
    # Проверяем без учета регистра
    for key, currency in COUNTRY_TO_CURRENCY.items():
        if key.lower() == country_normalized.lower():
            return currency
    
    # Если не найдено, возвращаем None
    return None


if __name__ == "__main__":
    data = get_current_rate(default="RUB", currencies=["USD", "EUR", "GBP", "JPY", "CNY"])
    if data and "quotes" in data:
        print(data["quotes"])
    else:
        print("Не удалось получить данные о курсах валют")
