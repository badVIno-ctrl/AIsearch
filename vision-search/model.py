# -*- coding: utf-8 -*-
#
# model.py — всё, что связано с нейросетями.
#
# Здесь лежит обёртка над CLIP (превращает картинки и текст в векторы),
# OCR (читаем текст прямо с картинок) и автотегирование (зеро-шот, то
# есть сеть сама решает, что на фото, без дообучения).
#
# Важный момент про мультиязычность: картинки кодирует обычный CLIP
# (clip-ViT-B-32), а текст — мультиязычный текстовый энкодер, который
# обучен в том же векторном пространстве. Благодаря этому русские
# запросы (и ещё ~50 языков) работают наравне с английскими.

import os
import threading

import numpy as np

# Модели можно переопределить через переменные окружения, но дефолты хорошие.
IMAGE_MODEL = os.environ.get("CLIP_IMAGE_MODEL", "clip-ViT-B-32")
TEXT_MODEL = os.environ.get("CLIP_TEXT_MODEL", "sentence-transformers/clip-ViT-B-32-multilingual-v1")

# Куда складывать скачанные веса моделей. Если рядом лежит папка models/
# — берём модель оттуда (оффлайн-режим, см. download_model.py).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_MODELS = os.path.join(BASE_DIR, "models")
if os.path.isdir(LOCAL_MODELS):
    # HuggingFace будет искать кэш здесь — значит интернет на запуске не нужен.
    os.environ.setdefault("HF_HOME", LOCAL_MODELS)
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", LOCAL_MODELS)


class VisionModel:
    """Ленивая обёртка над нейросетями.

    Модели тяжёлые, поэтому грузим их только при первом обращении и
    один раз. Все методы возвращают уже нормированные векторы.
    """

    def __init__(self):
        self._img_model = None
        self._txt_model = None
        self._lock = threading.Lock()  # чтобы два запроса не грузили модель одновременно

    # -- загрузка моделей --------------------------------------------------
    def _ensure_loaded(self):
        if self._img_model is not None:
            return
        with self._lock:
            if self._img_model is not None:
                return
            from sentence_transformers import SentenceTransformer

            print(f"[model] гружу модель картинок: {IMAGE_MODEL}", flush=True)
            self._img_model = SentenceTransformer(IMAGE_MODEL)
            print(f"[model] гружу текстовую (мультиязычную) модель: {TEXT_MODEL}", flush=True)
            self._txt_model = SentenceTransformer(TEXT_MODEL)
            print("[model] готово.", flush=True)

    # -- кодирование -----------------------------------------------------
    def encode_images(self, pil_images, batch_size=32, progress_cb=None):
        """Превратить список картинок PIL в матрицу векторов.

        progress_cb(done, total) — необязательный коллбэк, чтобы рисовать
        прогресс-бар индексации в интерфейсе.
        """
        self._ensure_loaded()
        if not pil_images:
            return np.zeros((0, 512), dtype=np.float32)
        total = len(pil_images)
        chunks = []
        done = 0
        # Идём пачками сами, чтобы честно сообщать прогресс.
        for start in range(0, total, batch_size):
            batch = pil_images[start:start + batch_size]
            vecs = self._img_model.encode(
                batch, convert_to_numpy=True, normalize_embeddings=True,
                show_progress_bar=False,
            )
            chunks.append(np.asarray(vecs, dtype=np.float32))
            done += len(batch)
            if progress_cb:
                progress_cb(done, total)
        return np.vstack(chunks)

    def encode_text(self, text):
        """Превратить текстовый запрос в вектор (любой язык)."""
        self._ensure_loaded()
        vec = self._txt_model.encode(
            [text], convert_to_numpy=True, normalize_embeddings=True,
        )[0]
        return np.asarray(vec, dtype=np.float32)

    def encode_image(self, pil_image):
        """Превратить одну картинку в вектор (поиск по загруженному фото)."""
        self._ensure_loaded()
        vec = self._img_model.encode(
            [pil_image], convert_to_numpy=True, normalize_embeddings=True,
        )[0]
        return np.asarray(vec, dtype=np.float32)

    # -- автотеги (zero-shot) ------------------------------------------------
    def tag_images(self, image_vectors, labels, top_n=3, min_score=0.18):
        """Подобрать к каждой картинке наиболее подходящие теги из списка.

        Работает без дообучения: кодируем текстовые метки в том же
        пространстве и смотрим, какая метка ближе всего к картинке.
        Возвращает список списков тегов (по одному на картинку).
        """
        self._ensure_loaded()
        if image_vectors is None or len(image_vectors) == 0 or not labels:
            return []
        label_vecs = self._txt_model.encode(
            labels, convert_to_numpy=True, normalize_embeddings=True,
        ).astype(np.float32)
        sims = np.asarray(image_vectors, dtype=np.float32) @ label_vecs.T
        tags = []
        for row in sims:
            order = np.argsort(-row)[:top_n]
            picked = [labels[i] for i in order if row[i] >= min_score]
            tags.append(picked)
        return tags


# --------------------------------------------------------------------------
# OCR — чтение текста с картинок (скриншоты, мемы, документы).
# --------------------------------------------------------------------------
# OCR требует внешний движок tesseract. Если его нет — просто молча
# отключаемся, чтобы приложение не падало. OCR — приятный бонус, а не
# обязательная часть.

_ocr_checked = False
_ocr_available = False


def ocr_available():
    """Есть ли в системе рабочий OCR (pytesseract + движок tesseract)."""
    global _ocr_checked, _ocr_available
    if _ocr_checked:
        return _ocr_available
    _ocr_checked = True
    try:
        import pytesseract  # type: ignore
        pytesseract.get_tesseract_version()
        _ocr_available = True
    except Exception:
        _ocr_available = False
    return _ocr_available


def ocr_text(pil_image, langs="rus+eng"):
    """Вытащить текст с картинки. Если OCR недоступен — вернём пустую строку."""
    if not ocr_available():
        return ""
    try:
        import pytesseract  # type: ignore
        return pytesseract.image_to_string(pil_image, lang=langs).strip()
    except Exception:
        # Например, не установлен языковой пакет — пробуем хотя бы eng.
        try:
            import pytesseract  # type: ignore
            return pytesseract.image_to_string(pil_image).strip()
        except Exception:
            return ""


# Список меток для автотегирования по умолчанию. Можно расширять под себя.
DEFAULT_TAGS = [
    "cat", "dog", "bird", "fish", "horse", "wild animal", "insect",
    "food", "fruit", "vegetable", "dessert", "drink",
    "car", "vehicle", "airplane", "boat", "train",
    "tree", "flower", "plant", "landscape", "sky", "weather",
    "person", "face", "building", "house",
    "sport", "music", "technology", "gadget", "tool",
    "text", "screenshot", "document", "logo", "drawing",
]
