# -*- coding: utf-8 -*-
#
# download_model.py — скачать модели заранее, чтобы потом работать оффлайн.
#
# Запусти один раз на компьютере с интернетом:
#     python download_model.py
# Модели лягут в папку ./models. После этого приложение можно
# запускать без сети (и даже перенести на другой компьютер вместе с models/).

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Говорим HuggingFace складывать всё сюда.
os.environ["HF_HOME"] = MODELS_DIR
os.environ["SENTENCE_TRANSFORMERS_HOME"] = MODELS_DIR

from model import IMAGE_MODEL, TEXT_MODEL  # noqa: E402


def main():
    from sentence_transformers import SentenceTransformer

    print(f"Скачиваю модель картинок: {IMAGE_MODEL}")
    SentenceTransformer(IMAGE_MODEL)
    print(f"Скачиваю текстовую модель: {TEXT_MODEL}")
    SentenceTransformer(TEXT_MODEL)
    print(f"Готово! Модели лежат в {MODELS_DIR}. Теперь можно запускаться оффлайн.")


if __name__ == "__main__":
    main()
