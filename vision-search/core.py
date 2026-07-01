# -*- coding: utf-8 -*-
#
# core.py — «сердце» приложения без тяжёлых зависимостей.
#
# Тут живёт вся математика и работа с файлами, которую можно спокойно
# протестировать без нейросети: хранение векторов, косинусный поиск,
# гибридный запрос (текст + фото), перцептивный хэш для поиска дубликатов
# и утилиты для сканирования папки. Ничего из torch/flask здесь нет —
# только numpy и PIL. Так проще тестировать и быстрее импортировать.

import os
import hashlib

import numpy as np
from PIL import Image

# Какие расширения считаем картинками. Остальное в папке игнорируем.
VALID_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif"}


def list_images(folder):
    """Собрать отсортированный список картинок в папке (без рекурсии)."""
    if not folder or not os.path.isdir(folder):
        return []
    files = []
    for name in sorted(os.listdir(folder)):
        ext = os.path.splitext(name)[1].lower()
        if ext in VALID_EXT:
            files.append(name)
    return files


def folder_signature(folder, files):
    """«Отпечаток» папки: имена + размеры + время правки.

    Нужен, чтобы понимать, поменялось ли что-то с прошлого запуска и не
    гонять индексацию заново, если папка не тронута.
    """
    h = hashlib.sha256()
    for f in files:
        try:
            st = os.stat(os.path.join(folder, f))
        except OSError:
            continue
        h.update(f.encode("utf-8"))
        h.update(str(int(st.st_size)).encode())
        h.update(str(int(st.st_mtime)).encode())
    return h.hexdigest()


def l2_normalize(vectors):
    """Привести векторы к единичной длине.

    После этого скалярное произведение = косинусная близость, что нам и надо.
    Работает и с одним вектором, и с целой матрицей (N, D).
    """
    v = np.asarray(vectors, dtype=np.float32)
    if v.ndim == 1:
        n = np.linalg.norm(v)
        return v / n if n > 0 else v
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # чтобы не делить на ноль на пустых векторах
    return v / norms


def combine_vectors(text_vec, image_vec, text_weight=0.5):
    """Смешать текстовый и картиночный запрос в один (гибридный поиск).

    text_weight=0.7 → «слушаем в основном текст», 0.3 → «в основном фото».
    Результат снова нормируем, иначе близости поедут.
    """
    if text_vec is None:
        return l2_normalize(image_vec)
    if image_vec is None:
        return l2_normalize(text_vec)
    w = float(max(0.0, min(1.0, text_weight)))
    mix = w * l2_normalize(text_vec) + (1.0 - w) * l2_normalize(image_vec)
    return l2_normalize(mix)


class VectorIndex:
    """Хранилище эмбеддингов картинок + быстрый поиск ближайших.

    Если в системе есть faiss — используем его (это заметно быстрее на
    больших коллекциях). Если нет — спокойно падаем на numpy, результат
    тот же, просто чуть медленнее. Для пользователя разницы никакой.
    """

    def __init__(self, use_faiss=True):
        self.files = []              # имена файлов, порядок совпадает с emb
        self.emb = None              # матрица (N, D), векторы уже нормированы
        self._faiss_index = None
        self._use_faiss = use_faiss

    def __len__(self):
        return len(self.files)

    def build(self, files, embeddings):
        """Заполнить индекс готовыми именами и векторами."""
        self.files = list(files)
        self.emb = l2_normalize(embeddings) if len(files) else None
        self._faiss_index = None
        if self._use_faiss and self.emb is not None and len(self.files) > 0:
            self._try_build_faiss()

    def _try_build_faiss(self):
        # faiss ставится не у всех, поэтому импорт «мягкий».
        try:
            import faiss  # type: ignore

            dim = self.emb.shape[1]
            index = faiss.IndexFlatIP(dim)  # inner product = косинус (мы нормированы)
            index.add(self.emb)
            self._faiss_index = index
        except Exception:
            # Нет faiss или что-то пошло не так — не страшно, поедем на numpy.
            self._faiss_index = None

    def search(self, query_vec, top_k=24, min_score=0.0, exclude=None):
        """Найти top_k ближайших картинок к вектору запроса.

        min_score отсекает слабые совпадения (слайдер порога в интерфейсе).
        exclude — набор имён, которые не показывать (например, само фото,
        по которому ищем «похожие»).
        """
        if self.emb is None or len(self.files) == 0:
            return []
        q = l2_normalize(query_vec).reshape(-1).astype(np.float32)
        exclude = exclude or set()

        # Берём с запасом, потому что часть результатов потом выкинем
        # порогом и exclude'ом.
        want = min(len(self.files), top_k + len(exclude) + 8)

        if self._faiss_index is not None:
            scores, idxs = self._faiss_index.search(q.reshape(1, -1), want)
            pairs = zip(idxs[0].tolist(), scores[0].tolist())
        else:
            sims = self.emb @ q
            take = min(len(sims), want)
            part = np.argpartition(-sims, take - 1)[:take]
            part = part[np.argsort(-sims[part])]
            pairs = ((int(i), float(sims[i])) for i in part)

        results = []
        for i, score in pairs:
            if i < 0 or i >= len(self.files):
                continue
            name = self.files[i]
            if name in exclude:
                continue
            if score < min_score:
                continue
            results.append({"file": name, "score": round(float(score), 4)})
            if len(results) >= top_k:
                break
        return results

    def vector_for(self, filename):
        """Достать сохранённый вектор конкретной картинки.

        Пригодится для кнопки «показать похожие на это» — не нужно гонять
        нейросеть заново, вектор уже посчитан при индексации.
        """
        if self.emb is None or filename not in self.files:
            return None
        return self.emb[self.files.index(filename)]


# --------------------------------------------------------------------------
# Поиск дубликатов через перцептивный хэш (dHash).
# --------------------------------------------------------------------------
# Идея простая: ужимаем картинку до 9x8, переводим в ч/б и смотрим, где
# соседний пиксель светлее предыдущего. Получается 64-битный «отпечаток».
# У похожих картинок отпечатки почти совпадают (маленькое расстояние
# Хэмминга), даже если у них разный размер или сжатие.

def dhash(image, hash_size=8):
    """Посчитать перцептивный хэш картинки (целое число, 64 бита)."""
    img = image.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
    px = np.asarray(img, dtype=np.int16)
    diff = px[:, 1:] > px[:, :-1]  # сравниваем соседние пиксели по строке
    bits = 0
    for bit in diff.flatten():
        bits = (bits << 1) | int(bool(bit))
    return bits


def hamming(a, b):
    """Расстояние Хэмминга между двумя хэшами — сколько битов различается."""
    return bin(a ^ b).count("1")


def find_duplicates(name_to_hash, max_distance=5):
    """Сгруппировать похожие картинки по их хэшам.

    Возвращает список групп (в каждой — 2+ похожих файла). max_distance —
    насколько сильно хэши могут отличаться, чтобы считать картинки «почти
    одинаковыми» (0 = пиксель в пиксель, больше = мягче).
    """
    items = list(name_to_hash.items())
    used = set()
    groups = []
    for i in range(len(items)):
        name_i, hash_i = items[i]
        if name_i in used:
            continue
        group = [name_i]
        for j in range(i + 1, len(items)):
            name_j, hash_j = items[j]
            if name_j in used:
                continue
            if hamming(hash_i, hash_j) <= max_distance:
                group.append(name_j)
                used.add(name_j)
        if len(group) > 1:
            used.add(name_i)
            groups.append(group)
    return groups
