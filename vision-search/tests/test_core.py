# -*- coding: utf-8 -*-
#
# Тесты на чистую логику core.py (без нейросети и сети).
#
# Запуск любым из двух способов:
#     python tests/test_core.py      (простой запуск, без pytest)
#     pytest                         (если pytest установлен)

import os
import sys

import numpy as np
from PIL import Image

# Чтобы import core работал при запуске из любой папки.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402


def test_l2_normalize():
    """После нормализации длина каждого вектора должна быть ~1."""
    v = np.array([[3.0, 4.0], [1.0, 0.0], [0.0, 0.0]], dtype=np.float32)
    n = core.l2_normalize(v)
    assert abs(np.linalg.norm(n[0]) - 1.0) < 1e-5
    assert abs(np.linalg.norm(n[1]) - 1.0) < 1e-5
    # Нулевой вектор не должен ломаться (нет деления на 0).
    assert not np.isnan(n[2]).any()


def test_combine_vectors():
    """Гибридный вектор — смесь текста и картинки, тоже нормализован."""
    t = np.array([1.0, 0.0], dtype=np.float32)
    im = np.array([0.0, 1.0], dtype=np.float32)
    mix = core.combine_vectors(t, im, text_weight=0.5)
    assert abs(np.linalg.norm(mix) - 1.0) < 1e-5
    # С весом 1.0 должен получиться чисто текстовый вектор.
    only_text = core.combine_vectors(t, im, text_weight=1.0)
    assert abs(only_text[0] - 1.0) < 1e-5 and abs(only_text[1]) < 1e-5


def test_vector_index_search():
    """Поиск должен возвращать самый похожий вектор первым."""
    files = ["a.jpg", "b.jpg", "c.jpg"]
    emb = core.l2_normalize(np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.9, 0.1, 0.0],
    ], dtype=np.float32))
    idx = core.VectorIndex(use_faiss=False)
    idx.build(files, emb)
    assert len(idx) == 3

    q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    res = idx.search(q, top_k=3)
    assert res[0]["file"] == "a.jpg"           # точное совпадение — первое
    assert res[0]["score"] >= res[1]["score"]  # отсортировано по убыванию


def test_search_min_score_and_exclude():
    """Порог схожести и исключение файлов работают."""
    files = ["a.jpg", "b.jpg"]
    emb = core.l2_normalize(np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
    idx = core.VectorIndex(use_faiss=False)
    idx.build(files, emb)
    q = np.array([1.0, 0.0], dtype=np.float32)

    # С высоким порогом останется только точное совпадение.
    res = idx.search(q, top_k=5, min_score=0.5)
    assert [r["file"] for r in res] == ["a.jpg"]

    # Исключаем a.jpg — его в выдаче быть не должно.
    res2 = idx.search(q, top_k=5, exclude={"a.jpg"})
    assert "a.jpg" not in [r["file"] for r in res2]


def test_vector_for():
    """vector_for возвращает вектор по имени файла и None для неизвестного."""
    files = ["a.jpg", "b.jpg"]
    emb = core.l2_normalize(np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
    idx = core.VectorIndex(use_faiss=False)
    idx.build(files, emb)
    assert idx.vector_for("a.jpg") is not None
    assert idx.vector_for("нету.jpg") is None


def test_dhash_and_hamming():
    """Одинаковые картинки — одинаковый хэш; разные — разный."""
    black = Image.new("RGB", (64, 64), (0, 0, 0))
    white = Image.new("RGB", (64, 64), (255, 255, 255))
    h_black1 = core.dhash(black)
    h_black2 = core.dhash(black.copy())
    h_white = core.dhash(white)
    # Одинаковые картинки → расстояние 0.
    assert core.hamming(h_black1, h_black2) == 0
    # Градиентная картинка отличается от ровного фона.
    grad = Image.new("L", (16, 16))
    px = grad.load()
    for y in range(16):
        for x in range(16):
            px[x, y] = x * 16
    assert core.hamming(core.dhash(grad.convert("RGB")), h_white) >= 0


def test_find_duplicates():
    """Почти-одинаковые хэши должны попасть в одну группу."""
    hashes = {
        "x1.jpg": 0b0000,
        "x2.jpg": 0b0001,   # отличие в 1 бит — дубль x1
        "y.jpg": 0b1111,    # совсем другой
    }
    groups = core.find_duplicates(hashes, max_distance=1)
    assert len(groups) == 1
    assert set(groups[0]) == {"x1.jpg", "x2.jpg"}


def test_list_images_and_signature(tmp_path=None):
    """list_images видит только картинки и сортирует их; подпись меняется."""
    import tempfile
    d = tempfile.mkdtemp()
    Image.new("RGB", (8, 8), (10, 10, 10)).save(os.path.join(d, "b.jpg"))
    Image.new("RGB", (8, 8), (20, 20, 20)).save(os.path.join(d, "a.png"))
    open(os.path.join(d, "readme.txt"), "w").write("not an image")
    files = core.list_images(d)
    assert files == ["a.png", "b.jpg"]          # только картинки, по алфавиту
    sig1 = core.folder_signature(d, files)
    # Добавим файл — подпись обязана поменяться.
    Image.new("RGB", (8, 8), (30, 30, 30)).save(os.path.join(d, "c.jpg"))
    files2 = core.list_images(d)
    sig2 = core.folder_signature(d, files2)
    assert sig1 != sig2


def _run_all():
    """Простой запуск без pytest: находим все test_* и выполняем."""
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            raise
    print(f"\nВсе тесты пройдены: {passed}/{len(tests)}")


if __name__ == "__main__":
    _run_all()
