# -*- coding: utf-8 -*-
#
# gen_images.py — генератор демо-базы картинок.
#
# Нужен только для того, чтобы было на чём показать поиск «из коробки».
# Каждая картинка — цветной градиент + крупная эмодзи по центру.
# Эмодзи — это удобно: у каждой есть чёткое значение (кот, пицца, ракета),
# так что легко проверить, что нейропоиск работает (запрос «кот» → котики).
#
#     Запуск:  python gen_images.py [сколько]
# Файлы ложатся в папку images/ видом 001_cat.jpg, 002_dog.jpg и т.д.

import os
import sys
import math
import random

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "images")
SIZE = 512                 # сторона квадратной картинки
EMOJI_NATIVE = 109         # шрифт NotoColorEmoji рисует только в этом размере

# Словарь «эмодзи -> латинское имя для файла».
# Набор широкий, чтобы было что искать: животные, еда, транспорт,
# природа, спорт, предметы, символы и т.д.
EMOJI = [
    ("🐱", "cat"), ("🐶", "dog"), ("🦊", "fox"), ("🐼", "panda"), ("🐨", "koala"),
    ("🦁", "lion"), ("🐯", "tiger"), ("🐴", "horse"), ("🦄", "unicorn"), ("🐷", "pig"),
    ("🐮", "cow"), ("🐑", "sheep"), ("🐐", "goat"), ("🐪", "camel"), ("🐘", "elephant"),
    ("🦏", "rhino"), ("🦓", "zebra"), ("🦒", "giraffe"), ("🐵", "monkey"), ("🦧", "gorilla"),
    ("🐸", "frog"), ("🐢", "turtle"), ("🐍", "snake"), ("🦎", "lizard"), ("🐊", "crocodile"),
    ("🐙", "octopus"), ("🦑", "squid"), ("🦐", "shrimp"), ("🦀", "crab"), ("🐟", "fish"),
    ("🐠", "tropical_fish"), ("🐡", "blowfish"), ("🐬", "dolphin"), ("🐳", "whale"), ("🦈", "shark"),
    ("🐌", "snail"), ("🦋", "butterfly"), ("🐛", "bug"), ("🐝", "bee"), ("🐞", "ladybug"),
    ("🕷", "spider"), ("🦂", "scorpion"), ("🦅", "eagle"), ("🐦", "bird"), ("🐧", "penguin"),
    ("🦉", "owl"), ("🦜", "parrot"), ("🐔", "chicken"), ("🦆", "duck"), ("🦚", "peacock"),
    ("🍎", "apple"), ("🍌", "banana"), ("🍇", "grapes"), ("🍉", "watermelon"), ("🍊", "orange"),
    ("🍋", "lemon"), ("🍑", "peach"), ("🍒", "cherries"), ("🍓", "strawberry"), ("🥝", "kiwi"),
    ("🍍", "pineapple"), ("🥝", "melon"), ("🥑", "avocado"), ("🍅", "tomato"), ("🍆", "eggplant"),
    ("🥕", "carrot"), ("🌽", "corn"), ("🌶", "pepper"), ("🥒", "cucumber"), ("🥦", "broccoli"),
    ("🍄", "mushroom"), ("🥐", "bread"), ("🥐", "croissant"), ("🥯", "bagel"), ("🥞", "pancakes"),
    ("🧀", "cheese"), ("🍖", "meat"), ("🍗", "poultry"), ("🥓", "bacon"), ("🍔", "burger"),
    ("🍟", "fries"), ("🍕", "pizza"), ("🌭", "hotdog"), ("🌮", "taco"), ("🌯", "burrito"),
    ("🥙", "falafel"), ("🥚", "egg"), ("🍳", "fried_egg"), ("🍲", "soup"), ("🍜", "ramen"),
    ("🍝", "spaghetti"), ("🍛", "bento"), ("🍚", "rice"), ("🍛", "curry"), ("🍣", "sushi"),
    ("🍤", "tempura"), ("🥫", "canned_food"), ("🍦", "ice_cream"), ("🍰", "cake"), ("🧁", "cupcake"),
    ("🍩", "donut"), ("🍪", "cookie"), ("🍫", "chocolate"), ("🍬", "candy"), ("🍭", "lollipop"),
    ("☕", "coffee"), ("🍵", "tea"), ("🧃", "juice"), ("🥛", "milk"), ("🍺", "beer"),
    ("🍷", "wine"), ("🍸", "cocktail"), ("🥂", "champagne"), ("🍾", "bottle"), ("🧊", "ice"),
    ("🚗", "car"), ("🚕", "taxi"), ("🚙", "suv"), ("🚌", "bus"), ("🚒", "fire_truck"),
    ("🚑", "ambulance"), ("🚓", "police_car"), ("🚜", "tractor"), ("🛵", "scooter"), ("🏍", "motorcycle"),
    ("🚲", "bicycle"), ("🚂", "train"), ("🚅", "metro"), ("🚊", "tram"), ("✈", "airplane"),
    ("🚁", "helicopter"), ("🚀", "rocket"), ("🛸", "ufo"), ("⛵", "sailboat"), ("🚤", "speedboat"),
    ("🚢", "ship"), ("⚓", "anchor"), ("🚏", "bus_stop"), ("🚦", "traffic_light"), ("🗽", "statue_of_liberty"),
    ("🌍", "earth"), ("🌞", "sun"), ("🌙", "moon"), ("⭐", "star"), ("🌠", "shooting_star"),
    ("⚡", "lightning"), ("🔥", "fire"), ("💧", "droplet"), ("❄", "snowflake"), ("🌈", "rainbow"),
    ("☁", "cloud"), ("⛅", "partly_cloudy"), ("🌊", "wave"), ("🌋", "volcano"), ("🏔", "mountain"),
    ("🌵", "cactus"), ("🌴", "palm_tree"), ("🌲", "evergreen"), ("🌳", "tree"), ("🍀", "clover"),
    ("🌷", "tulip"), ("🌸", "blossom"), ("🌹", "rose"), ("🌻", "sunflower"), ("🌼", "daisy"),
    ("🍂", "leaf"), ("🍁", "maple_leaf"), ("🍄", "toadstool"), ("🌾", "wheat"), ("🌱", "seedling"),
    ("⚽", "soccer"), ("🏀", "basketball"), ("🏈", "football"), ("⚾", "baseball"), ("🎾", "tennis"),
    ("🏐", "volleyball"), ("🎱", "billiards"), ("🏓", "pingpong"), ("🏸", "badminton"), ("🥊", "boxing"),
    ("🎿", "ski"), ("⛸", "ice_skate"), ("🏄", "surfing"), ("🏊", "swimming"), ("🤿", "diving"),
    ("🎸", "guitar"), ("🎹", "piano"), ("🎺", "trumpet"), ("🎻", "violin"), ("🥁", "drum"),
    ("🎤", "microphone"), ("🎧", "headphones"), ("🎵", "music"), ("🎬", "movie"), ("🎨", "art"),
    ("📷", "camera"), ("💻", "laptop"), ("🖥", "desktop"), ("📱", "phone"), ("⌚", "watch"),
    ("🕯", "candle"), ("💡", "bulb"), ("🔦", "flashlight"), ("🔋", "battery"), ("🧩", "puzzle"),
    ("🎮", "game"), ("🎲", "dice"), ("🎯", "target"), ("🏹", "bow"), ("🪁", "kite"),
    ("📦", "box"), ("🎁", "gift"), ("🎈", "balloon"), ("🎉", "party"), ("🎪", "circus"),
    ("👑", "crown"), ("💎", "gem"), ("💍", "ring"), ("👜", "handbag"), ("👟", "sneaker"),
    ("👗", "dress"), ("👕", "tshirt"), ("👒", "hat"), ("🧣", "scarf"), ("🕶", "sunglasses"),
    ("❤", "heart"), ("💙", "blue_heart"), ("💚", "green_heart"), ("💛", "yellow_heart"), ("🧡", "orange_heart"),
    ("🔑", "key"), ("🔒", "lock"), ("🔍", "magnifier"), ("✂", "scissors"), ("📌", "pushpin"),
    ("✏", "pencil"), ("📚", "books"), ("📖", "open_book"), ("✉", "envelope"), ("💰", "money_bag"),
]

# Красивые пары цветов для градиентов фона (RGB → RGB).
GRADIENTS = [
    ((255, 94, 98), (255, 195, 113)), ((131, 96, 195), (46, 191, 145)),
    ((252, 92, 125), (106, 130, 251)), ((17, 153, 142), (56, 239, 125)),
    ((255, 128, 8), (255, 200, 55)), ((0, 201, 255), (146, 254, 157)),
    ((238, 9, 121), (255, 106, 0)), ((44, 62, 80), (76, 161, 175)),
    ((170, 75, 107), (107, 107, 131)), ((0, 4, 40), (0, 78, 146)),
    ((255, 0, 150), (0, 204, 255)), ((22, 191, 253), (203, 48, 102)),
]


def find_emoji_font():
    """Ищем цветной эмодзи-шрифт в типичных местах разных ОС."""
    candidates = [
        "/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "C:/Windows/Fonts/seguiemj.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def make_gradient(c1, c2):
    """Диагональный градиент из двух цветов."""
    base = Image.new("RGB", (SIZE, SIZE), c1)
    top = Image.new("RGB", (SIZE, SIZE), c2)
    mask = Image.new("L", (SIZE, SIZE))
    md = mask.load()
    for y in range(SIZE):
        for x in range(SIZE):
            md[x, y] = int(255 * ((x + y) / (2 * SIZE)))
    base.paste(top, (0, 0), mask)
    return base


def draw_emoji(img, emoji, font):
    """Рисуем эмодзи по центру. Шрифт Noto умеет только 109px,
    поэтому рисуем на отдельном слое и потом увеличиваем."""
    layer = Image.new("RGBA", (EMOJI_NATIVE * 2, EMOJI_NATIVE * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    try:
        d.text((EMOJI_NATIVE, EMOJI_NATIVE), emoji, font=font,
               anchor="mm", embedded_color=True)
    except Exception:
        d.text((EMOJI_NATIVE, EMOJI_NATIVE), emoji, font=font, anchor="mm")
    scaled = layer.resize((int(SIZE * 0.62), int(SIZE * 0.62)), Image.LANCZOS)
    pos = ((SIZE - scaled.width) // 2, (SIZE - scaled.height) // 2)
    img.paste(scaled, pos, scaled)


def draw_fallback(img, name):
    """Если эмодзи-шрифта нет — пишем крупную подпись текстом."""
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 56)
    except Exception:
        font = ImageFont.load_default()
    d.text((SIZE // 2, SIZE // 2), name.replace("_", "\n"),
           font=font, anchor="mm", align="center", fill=(255, 255, 255))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    random.seed(7)   # фиксируем seed — генерация воспроизводимая

    # Сколько картинок делать (по умолчанию — весь список).
    count = int(sys.argv[1]) if len(sys.argv) > 1 else len(EMOJI)
    count = min(count, len(EMOJI))

    font_path = find_emoji_font()
    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, EMOJI_NATIVE)
            print(f"Эмодзи-шрифт: {font_path}")
        except Exception as e:
            print("Не смог открыть эмодзи-шрифт:", e)
    if not font:
        print("Эмодзи-шрифт не найден — рисую подписи текстом.")

    for i in range(count):
        emoji, name = EMOJI[i]
        c1, c2 = random.choice(GRADIENTS)
        img = make_gradient(c1, c2)
        if font:
            draw_emoji(img, emoji, font)
        else:
            draw_fallback(img, name)
        fname = f"{i + 1:03d}_{name}.jpg"
        img.save(os.path.join(OUT_DIR, fname), "JPEG", quality=90)

    print(f"Готово! Создано {count} картинок в папке {OUT_DIR}")


if __name__ == "__main__":
    main()
