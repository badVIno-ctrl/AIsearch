# Vision Search в контейнере.
# Сборка:   docker build -t vision-search .
# Запуск:   docker run -p 5000:5000 -v /путь/к/фото:/app/images vision-search
# Потом открой http://127.0.0.1:5000

FROM python:3.11-slim

# tesseract — чтобы работал OCR (поиск по тексту внутри картинок).
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Сначала только зависимости — так Docker кэширует слой с pip install.
COPY requirements.txt optional-requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir pytesseract

# Теперь остальной код.
COPY . .

ENV HOST=0.0.0.0 PORT=5000 NO_BROWSER=1
EXPOSE 5000
CMD ["python", "app.py"]
