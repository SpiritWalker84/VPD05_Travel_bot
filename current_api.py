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
# Приоритет русским названиям
COUNTRY_TO_CURRENCY = {
    # Россия
    "Россия": "RUB", "Russia": "RUB", "RU": "RUB", "РФ": "RUB",
    # США
    "США": "USD", "Соединенные Штаты": "USD", "Соединенные Штаты Америки": "USD", 
    "USA": "USD", "United States": "USD", "US": "USD",
    # Евросоюз и страны ЕС
    "Евросоюз": "EUR", "ЕС": "EUR", "EU": "EUR", "Europe": "EUR",
    "Германия": "EUR", "Germany": "EUR", "DE": "EUR",
    "Франция": "EUR", "France": "EUR", "FR": "EUR",
    "Италия": "EUR", "Italy": "EUR", "IT": "EUR",
    "Испания": "EUR", "Spain": "EUR", "ES": "EUR",
    "Нидерланды": "EUR", "Netherlands": "EUR", "NL": "EUR",
    "Бельгия": "EUR", "Belgium": "EUR", "BE": "EUR",
    "Австрия": "EUR", "Austria": "EUR", "AT": "EUR",
    "Португалия": "EUR", "Portugal": "EUR", "PT": "EUR",
    "Греция": "EUR", "Greece": "EUR", "GR": "EUR",
    "Финляндия": "EUR", "Finland": "EUR", "FI": "EUR",
    "Ирландия": "EUR", "Ireland": "EUR", "IE": "EUR",
    # Великобритания
    "Великобритания": "GBP", "Англия": "GBP", "UK": "GBP", 
    "United Kingdom": "GBP", "GB": "GBP",
    # Китай
    "Китай": "CNY", "КНР": "CNY", "China": "CNY", "CN": "CNY",
    # Япония
    "Япония": "JPY", "Japan": "JPY", "JP": "JPY",
    # Другие страны
    "Канада": "CAD", "Canada": "CAD", "CA": "CAD",
    "Австралия": "AUD", "Australia": "AUD", "AU": "AUD",
    "Швейцария": "CHF", "Switzerland": "CHF", "CH": "CHF",
    "Турция": "TRY", "Turkey": "TRY", "TR": "TRY",
    "Индия": "INR", "India": "INR", "IN": "INR",
    "Бразилия": "BRL", "Brazil": "BRL", "BR": "BRL",
    "Мексика": "MXN", "Mexico": "MXN", "MX": "MXN",
    "Южная Корея": "KRW", "Корея": "KRW", "South Korea": "KRW", "KR": "KRW",
    "Сингапур": "SGD", "Singapore": "SGD", "SG": "SGD",
    "Таиланд": "THB", "Thailand": "THB", "TH": "THB",
    "ОАЭ": "AED", "Объединенные Арабские Эмираты": "AED", 
    "UAE": "AED", "United Arab Emirates": "AED", "AE": "AED",
    "Саудовская Аравия": "SAR", "Saudi Arabia": "SAR", "SA": "SAR",
    "Норвегия": "NOK", "Norway": "NOK", "NO": "NOK",
    "Швеция": "SEK", "Sweden": "SEK", "SE": "SEK",
    "Дания": "DKK", "Denmark": "DKK", "DK": "DKK",
    "Польша": "PLN", "Poland": "PLN", "PL": "PLN",
    "Чехия": "CZK", "Czech Republic": "CZK", "CZ": "CZK",
    "Венгрия": "HUF", "Hungary": "HUF", "HU": "HUF",
    "Израиль": "ILS", "Israel": "ILS", "IL": "ILS",
    "ЮАР": "ZAR", "Южно-Африканская Республика": "ZAR", 
    "South Africa": "ZAR", "ZA": "ZAR",
    "Новая Зеландия": "NZD", "New Zealand": "NZD", "NZ": "NZD",
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
    
    # Сначала проверяем точное совпадение (приоритет русским названиям)
    if country_normalized in COUNTRY_TO_CURRENCY:
        return COUNTRY_TO_CURRENCY[country_normalized]
    
    # Проверяем без учета регистра
    for key, currency in COUNTRY_TO_CURRENCY.items():
        if key.lower() == country_normalized.lower():
            return currency
    
    # Проверяем частичное совпадение (для случаев типа "Соединенные Штаты Америки")
    country_lower = country_normalized.lower()
    for key, currency in COUNTRY_TO_CURRENCY.items():
        key_lower = key.lower()
        if country_lower in key_lower or key_lower in country_lower:
            return currency
    
    # Если не найдено, возвращаем None
    return None


if __name__ == "__main__":
    data = get_current_rate(default="RUB", currencies=["USD", "EUR", "GBP", "JPY", "CNY"])
    if data and "quotes" in data:
        print(data["quotes"])
    else:
        print("Не удалось получить данные о курсах валют")
