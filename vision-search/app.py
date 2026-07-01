# -*- coding: utf-8 -*-
#
# app.py — веб-сервер (Flask). Он связывает всё вместе:
#   • держит индекс картинок в памяти (core.VectorIndex),
#   • общается с нейросетью (model.VisionModel),
#   • отдаёт фронтенд и отвечает на запросы поиска.
#
# Индексация идёт в фоновом потоке, чтобы страница открывалась сразу,
# а пользователь видел честный прогресс-бар.

import io
import os
import sys
import json
import signal
import shutil
import threading
import subprocess
import webbrowser

import numpy as np
from PIL import Image
from flask import Flask, request, jsonify, send_from_directory, abort

import core
from model import VisionModel, ocr_text, ocr_available, DEFAULT_TAGS

# --------------------------------------------------------------------------
# Пути и настройки
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IMAGES_DIR = os.path.join(BASE_DIR, "images")
CACHE_DIR = os.path.join(BASE_DIR, ".cache")
CONFIG_FILE = os.path.join(CACHE_DIR, "config.json")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(DEFAULT_IMAGES_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # ограничение на размер загрузки

model = VisionModel()
index = core.VectorIndex(use_faiss=True)

# Общее состояние индекса. Меняется из фонового потока, поэтому
# прикрыто замком.
state = {
    "folder": DEFAULT_IMAGES_DIR,
    "status": "idle",     # idle | indexing | ready | error
    "done": 0,
    "total": 0,
    "error": "",
    "ocr": {},            # имя файла -> распознанный текст
    "tags": {},           # имя файла -> список тегов
    "hashes": {},         # имя файла -> перцептивный хэш
}
state_lock = threading.Lock()


def log(*a):
    print("[vision-search]", *a, flush=True)


# --------------------------------------------------------------------------
# Конфиг (запоминаем выбранную папку между запусками)
# --------------------------------------------------------------------------
def load_config():
    try:
        cfg = json.load(open(CONFIG_FILE, encoding="utf-8"))
        folder = cfg.get("folder")
        if folder and os.path.isdir(folder):
            state["folder"] = folder
    except Exception:
        pass


def save_config():
    try:
        json.dump({"folder": state["folder"]},
                  open(CONFIG_FILE, "w", encoding="utf-8"))
    except Exception as e:
        log("не удалось сохранить конфиг:", e)


def cache_paths(folder):
    """Пути к кэшу для конкретной папки (у каждой папки свой кэш)."""
    key = core.hashlib.sha256(folder.encode("utf-8")).hexdigest()[:16]
    return (os.path.join(CACHE_DIR, f"emb_{key}.npy"),
            os.path.join(CACHE_DIR, f"meta_{key}.json"))


# --------------------------------------------------------------------------
# Индексация
# --------------------------------------------------------------------------
def _set(**kw):
    """Короткий хелпер, чтобы обновить состояние под замком."""
    with state_lock:
        state.update(kw)


def build_index(folder, force=False):
    """Посчитать (или достать из кэша) векторы для всех картинок папки.

    Вызывается из фонового потока, поэтому аккуратно обновляет state.
    """
    files = core.list_images(folder)
    sig = core.folder_signature(folder, files) if files else "empty"
    emb_file, meta_file = cache_paths(folder)

    # 1) Пробуем взять из кэша, если папка не менялась.
    if not force and os.path.exists(emb_file) and os.path.exists(meta_file):
        try:
            meta = json.load(open(meta_file, encoding="utf-8"))
            if meta.get("signature") == sig and meta.get("files") == files:
                emb = np.load(emb_file)
                index.build(files, emb)
                _set(status="ready", done=len(files), total=len(files),
                     ocr=meta.get("ocr", {}), tags=meta.get("tags", {}),
                     hashes={k: int(v) for k, v in meta.get("hashes", {}).items()})
                log(f"взял индекс из кэша ({len(files)} фото).")
                return
        except Exception as e:
            log("кэш не подошёл, пересчитываю:", e)

    # 2) Пустая папка — просто очищаем индекс.
    if not files:
        index.build([], np.zeros((0, 512), dtype=np.float32))
        _set(status="ready", done=0, total=0, ocr={}, tags={}, hashes={})
        log("в папке нет картинок.")
        return

    # 3) Считаем заново.
    _set(status="indexing", done=0, total=len(files), error="")
    log(f"индексирую {len(files)} картинок...")

    pil_images, kept, hashes, ocr = [], [], {}, {}
    do_ocr = ocr_available()
    for name in files:
        path = os.path.join(folder, name)
        try:
            im = Image.open(path).convert("RGB")
        except Exception as e:
            log("пропускаю", name, e)
            continue
        pil_images.append(im)
        kept.append(name)
        hashes[name] = core.dhash(im)          # для поиска дубликатов
        if do_ocr:
            ocr[name] = ocr_text(im)           # текст внутри картинки

    def progress(done, total):
        _set(done=done, total=total)

    emb = model.encode_images(pil_images, progress_cb=progress)

    # Автотеги: подписываем, что на каждой картинке.
    tags_list = model.tag_images(emb, DEFAULT_TAGS)
    tags = {kept[i]: tags_list[i] for i in range(len(kept))} if tags_list else {}

    index.build(kept, emb)

    # Сохраняем кэш, чтобы следующий запуск был мгновенным.
    np.save(emb_file, index.emb)
    json.dump({"signature": sig, "files": kept, "ocr": ocr, "tags": tags,
               "hashes": {k: str(v) for k, v in hashes.items()}},
              open(meta_file, "w", encoding="utf-8"))

    _set(status="ready", done=len(kept), total=len(kept),
         ocr=ocr, tags=tags, hashes=hashes)
    log(f"индекс готов ({len(kept)} фото).")


def start_indexing(folder, force=False):
    """Запустить индексацию в отдельном потоке (не блокируя сервер)."""
    def worker():
        try:
            build_index(folder, force=force)
        except Exception as e:
            log("ошибка индексации:", e)
            _set(status="error", error=str(e))
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


# --------------------------------------------------------------------------
# Роуты: страница и файлы
# --------------------------------------------------------------------------
@app.route("/")
def home():
    return send_from_directory("templates", "index.html")


@app.route("/images/<path:filename>")
def serve_image(filename):
    # Отдаём картинку из текущей рабочей папки.
    return send_from_directory(state["folder"], filename)


# --------------------------------------------------------------------------
# Роуты: статус и галерея
# --------------------------------------------------------------------------
@app.route("/api/status")
def api_status():
    with state_lock:
        total = state["total"]
        done = state["done"]
        pct = int(done * 100 / total) if total else (100 if state["status"] == "ready" else 0)
        return jsonify({
            "status": state["status"],
            "ready": state["status"] == "ready",
            "done": done,
            "total": total,
            "percent": pct,
            "count": len(index),
            "folder": state["folder"],
            "ocr_enabled": ocr_available(),
            "error": state["error"],
        })


@app.route("/api/gallery")
def api_gallery():
    with state_lock:
        tags = state["tags"]
    return jsonify({"images": [{"file": f, "tags": tags.get(f, [])} for f in index.files],
                    "count": len(index)})


# --------------------------------------------------------------------------
# Роуты: поиск
# --------------------------------------------------------------------------
def _ocr_matches(query):
    """Найти картинки, в тексте которых (OCR) встречается запрос."""
    q = query.strip().lower()
    if not q:
        return []
    with state_lock:
        ocr = state["ocr"]
    hits = []
    for name, text in ocr.items():
        if text and q in text.lower():
            hits.append(name)
    return hits


@app.route("/api/search/text", methods=["POST"])
def api_search_text():
    data = request.get_json(force=True, silent=True) or {}
    query = (data.get("query") or "").strip()
    top_k = int(data.get("top_k") or 24)
    min_score = float(data.get("min_score") or 0.0)
    if not query:
        return jsonify({"error": "пустой запрос"}), 400
    if state["status"] != "ready":
        return jsonify({"error": "индекс ещё не готов", "status": state["status"]}), 503

    vec = model.encode_text(query)
    results = index.search(vec, top_k=top_k, min_score=min_score)

    # Докидываем совпадения по тексту внутри картинок (OCR) — они очень
    # точные, поэтому поднимаем их наверх.
    ocr_hits = _ocr_matches(query)
    if ocr_hits:
        existing = {r["file"] for r in results}
        extra = [{"file": n, "score": 1.0, "ocr": True}
                 for n in ocr_hits if n not in existing]
        results = extra + results

    return jsonify({"query": query, "results": results})


@app.route("/api/search/image", methods=["POST"])
def api_search_image():
    if state["status"] != "ready":
        return jsonify({"error": "индекс ещё не готов", "status": state["status"]}), 503
    top_k = int(request.form.get("top_k") or 24)
    min_score = float(request.form.get("min_score") or 0.0)
    text = (request.form.get("query") or "").strip()
    text_weight = float(request.form.get("text_weight") or 0.5)
    if "image" not in request.files:
        return jsonify({"error": "не передано изображение"}), 400
    try:
        im = Image.open(io.BytesIO(request.files["image"].read())).convert("RGB")
    except Exception as e:
        return jsonify({"error": f"не смог прочитать картинку: {e}"}), 400

    img_vec = model.encode_image(im)
    # Если вместе с фото пришёл текст — делаем гибридный запрос
    # («похоже на это фото, но ...»).
    if text:
        txt_vec = model.encode_text(text)
        query_vec = core.combine_vectors(txt_vec, img_vec, text_weight=text_weight)
    else:
        query_vec = img_vec
    results = index.search(query_vec, top_k=top_k, min_score=min_score)
    return jsonify({"results": results})


@app.route("/api/similar", methods=["POST"])
def api_similar():
    """Показать картинки, похожие на уже проиндексированную (кнопка «похожие»)."""
    data = request.get_json(force=True, silent=True) or {}
    filename = data.get("file")
    top_k = int(data.get("top_k") or 24)
    if not filename:
        return jsonify({"error": "не указан файл"}), 400
    vec = index.vector_for(filename)
    if vec is None:
        return jsonify({"error": "файл не найден в индексе"}), 404
    # Саму картинку исключаем — нечего искать саму себя.
    results = index.search(vec, top_k=top_k, exclude={filename})
    return jsonify({"results": results})


@app.route("/api/duplicates", methods=["POST"])
def api_duplicates():
    """Найти группы почти-одинаковых картинок."""
    data = request.get_json(force=True, silent=True) or {}
    distance = int(data.get("distance") or 5)
    with state_lock:
        hashes = dict(state["hashes"])
    groups = core.find_duplicates(hashes, max_distance=distance)
    return jsonify({"groups": groups, "count": len(groups)})


# --------------------------------------------------------------------------
# Роуты: управление папкой и действия с файлами
# --------------------------------------------------------------------------
@app.route("/api/folder", methods=["POST"])
def api_folder():
    """Поменять рабочую папку и переиндексировать её."""
    data = request.get_json(force=True, silent=True) or {}
    folder = (data.get("folder") or "").strip()
    if not folder or not os.path.isdir(folder):
        return jsonify({"error": "папка не найдена"}), 400
    _set(folder=os.path.abspath(folder))
    save_config()
    start_indexing(state["folder"], force=False)
    return jsonify({"ok": True, "folder": state["folder"]})


@app.route("/api/reindex", methods=["POST"])
def api_reindex():
    """Пересчитать индекс текущей папки с нуля (кнопка в UI)."""
    start_indexing(state["folder"], force=True)
    return jsonify({"ok": True})


@app.route("/api/open", methods=["POST"])
def api_open():
    """Открыть файл в системном проводнике (локальное приложение — это ок)."""
    data = request.get_json(force=True, silent=True) or {}
    filename = data.get("file")
    if not filename:
        return jsonify({"error": "не указан файл"}), 400
    path = os.path.join(state["folder"], filename)
    if not os.path.isfile(path):
        return jsonify({"error": "файл не найден"}), 404
    try:
        if sys.platform.startswith("win"):
            os.startfile(os.path.normpath(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
        return jsonify({"ok": True, "path": os.path.abspath(path)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export", methods=["POST"])
def api_export():
    """Скопировать найденные картинки в отдельную папку (export/)."""
    data = request.get_json(force=True, silent=True) or {}
    files = data.get("files") or []
    subdir = (data.get("name") or "export").strip() or "export"
    dest = os.path.join(BASE_DIR, "exports", os.path.basename(subdir))
    os.makedirs(dest, exist_ok=True)
    copied = 0
    for name in files:
        src = os.path.join(state["folder"], name)
        if os.path.isfile(src):
            try:
                shutil.copy2(src, os.path.join(dest, os.path.basename(name)))
                copied += 1
            except Exception as e:
                log("не смог скопировать", name, e)
    return jsonify({"ok": True, "copied": copied, "dest": os.path.abspath(dest)})


@app.route("/api/path", methods=["POST"])
def api_path():
    """Вернуть абсолютный путь файла (чтобы скопировать в буфер)."""
    data = request.get_json(force=True, silent=True) or {}
    filename = data.get("file")
    if not filename:
        return jsonify({"error": "не указан файл"}), 400
    return jsonify({"path": os.path.abspath(os.path.join(state["folder"], filename))})


# --------------------------------------------------------------------------
# Запуск
# --------------------------------------------------------------------------
def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    load_config()

    log("стартую и запускаю индексацию в фоне...")
    start_indexing(state["folder"], force=False)

    url = f"http://{host}:{port}"
    log(f"сервер здесь:  {url}")

    # Аккуратно гаснем по Ctrl+C.
    def bye(signum, frame):
        log("останавливаюсь. Пока!")
        os._exit(0)
    signal.signal(signal.SIGINT, bye)
    try:
        signal.signal(signal.SIGTERM, bye)
    except Exception:
        pass

    # Открываем браузер автоматически через пару секунд.
    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
