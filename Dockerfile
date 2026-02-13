FROM python:3.14-slim

WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY bot.py database.py current_api.py ./

# Создаем директорию для базы данных
RUN mkdir -p /app/data

# Запускаем бота
CMD ["python", "bot.py"]
