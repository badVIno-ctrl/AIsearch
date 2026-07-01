# -*- coding: utf-8 -*-
#
# build_exe.py — собрать Windows-.exe, чтобы запускать вообще без Python.
#
# Как пользоваться (на машине с установленными зависимостями):
#     pip install pyinstaller
#     python build_exe.py
# Готовый exe появится в папке dist/.
#
# Важно: сама модель CLIP в exe не вшивается (она большая) — лучше
# сначала выполнить download_model.py и положить папку models/ рядом с exe.

import PyInstaller.__main__

PyInstaller.__main__.run([
    "app.py",
    "--name", "VisionSearch",
    "--onefile",
    "--noconfirm",
    # Кладём рядом фронтенд и базу картинок (разделитель путей на Windows — точка с запятой).
    "--add-data", "templates;templates",
    "--add-data", "static;static",
    # Некоторые пакеты PyInstaller не видит автоматически — подсказываем.
    "--collect-all", "sentence_transformers",
    "--collect-all", "tokenizers",
])
