from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExamMode:
    code: str
    title: str
    prompt_hint: str


EXAM_ROOT_BUTTON = "🎯 Подготовка ЕГЭ / ОГЭ / ВПР"
EXAM_MENU_BUTTON = "🎯 Подготовка к экзаменам"
EXAM_MENU_ALIASES = {
    EXAM_MENU_BUTTON,
    EXAM_ROOT_BUTTON,
    "Подготовка к экзаменам",
    "Подготовка ЕГЭ / ОГЭ / ВПР",
}

EXAM_SECTIONS = {"ege": "ЕГЭ", "oge": "ОГЭ", "vpr": "ВПР"}
EXAM_DISPLAY_NAMES = EXAM_SECTIONS.copy()

EXAM_SUBJECTS = {
    "ege": ["Русский язык", "Математика", "Обществознание", "Информатика", "Биология", "История", "Английский язык", "Физика", "Химия", "Литература", "География"],
    "oge": ["Русский язык", "Математика", "Обществознание", "Информатика", "Биология", "История", "Английский язык", "Физика", "Химия", "Литература", "География"],
    "vpr": ["Русский язык", "Математика", "Окружающий мир", "История", "Биология", "География", "Обществознание", "Физика"],
}
VPR_CLASSES = ["4 класс", "5 класс", "6 класс", "7 класс", "8 класс", "10 класс"]

TOPICS = {
    ("ege", "Русский язык"): ["Н/НН", "Пунктуация", "Сочинение", "Орфоэпия", "Паронимы", "Средства выразительности"],
    ("ege", "Математика"): ["Уравнения", "Неравенства", "Производная", "Тригонометрия", "Вероятность", "Стереометрия"],
    ("ege", "Обществознание"): ["Экономика", "Право", "Политика", "Социальная сфера", "Человек и общество", "Конституция"],
    ("ege", "Информатика"): ["Алгоритмы", "Циклы", "Массивы", "Рекурсия", "Системы счисления", "Логика"],
    ("oge", "Русский язык"): ["Изложение", "Сочинение 13.3", "Орфография", "Пунктуация", "Грамматическая основа", "Средства выразительности"],
    ("oge", "Математика"): ["Уравнения", "Неравенства", "Геометрия", "Графики функций", "Вероятность", "Текстовые задачи"],
    ("oge", "Обществознание"): ["Человек", "Общество", "Экономика", "Право", "Политика", "Социальная сфера"],
    ("oge", "Информатика"): ["Алгоритмы", "Исполнители", "Логика", "Кодирование", "Таблицы", "Программирование"],
    ("vpr", "Русский язык"): ["Орфограммы", "Главные члены предложения", "Пунктуация", "Текст и тема", "Части речи", "Разбор слова"],
    ("vpr", "Математика"): ["Дроби", "Уравнения", "Проценты", "Площадь и периметр", "Задачи на движение", "Графики"],
}

EXAM_MODES: dict[str, list[ExamMode]] = {
    "ege": [
        ExamMode("subject_cards", "📚 Карточки тем", "Карточки по теме с коротким объяснением."),
        ExamMode("daily_plan", "📅 Что учить сегодня", "План на день с блоками подготовки."),
        ExamMode("typical_errors", "⚠️ Типичные ошибки 2026", "Типичные ошибки и как их избежать."),
        ExamMode("mini_test", "🧪 Вариант на сегодня", "Мини-вариант из 5 заданий."),
        ExamMode("explain", "📖 Объяснить тему", "Объяснение темы простыми словами."),
        ExamMode("check_answer", "📝 Проверить ответ", "Проверка ответа по критериям."),
        ExamMode("speaking", "🎙 Мини-симулятор устной части", "Краткая тренировка устной части."),
        ExamMode("essay", "✍️ Итоговое сочинение", "План, структура и аргументы."),
        ExamMode("official", "📂 Официальные материалы", "Официальные материалы ФИПИ и Рособрнадзора."),
    ],
    "oge": [
        ExamMode("subject_cards", "📚 Карточки тем", "Карточки по теме с коротким объяснением."),
        ExamMode("daily_plan", "📅 Что учить сегодня", "План на день с блоками подготовки."),
        ExamMode("typical_errors", "⚠️ Типичные ошибки 2026", "Типичные ошибки и как их избежать."),
        ExamMode("mini_test", "🧪 Мини-вариант", "Мини-вариант из 5 заданий."),
        ExamMode("explain", "📖 Объяснить тему", "Объяснение темы простыми словами."),
        ExamMode("check_answer", "📝 Проверить ответ", "Проверка ответа по критериям."),
        ExamMode("speaking", "🎙 Мини-симулятор устной части", "Тренировка итогового собеседования."),
        ExamMode("essay", "🗣 Итоговое собеседование", "Монолог, диалог и критерии."),
        ExamMode("official", "📂 Официальные материалы", "Официальные материалы ФИПИ и Рособрнадзора."),
    ],
    "vpr": [
        ExamMode("subject_cards", "📚 Карточки тем", "Карточки по теме с коротким объяснением."),
        ExamMode("daily_plan", "📅 Что учить сегодня", "Короткий план на день."),
        ExamMode("typical_errors", "⚠️ Типичные ошибки 2026", "Частые школьные ошибки."),
        ExamMode("mini_test", "🧪 Мини-тест", "Короткая тренировка на сегодня."),
        ExamMode("explain", "📖 Объяснить тему", "Объяснение темы простыми словами."),
        ExamMode("check_answer", "📝 Проверить ответ", "Проверка ответа или фото."),
        ExamMode("official", "📂 Официальные материалы", "Официальные материалы."),
    ],
}

EXAM_SECTION_LINKS = {
    "ege": {
        "docs": "https://fipi.ru/ege/demoversii-specifikacii-kodifikatory",
        "bank": "https://ege.fipi.ru/bank/",
        "changes": "https://fipi.ru/ege",
        "essay": "https://obrnadzor.gov.ru/gia/gia-11/itogovoe-sochinenie-izlozhenie/",
    },
    "oge": {
        "docs": "https://fipi.ru/oge/demoversii-specifikacii-kodifikatory",
        "bank": "https://oge.fipi.ru/bank/index.php",
        "changes": "https://fipi.ru/oge",
        "interview": "https://obrnadzor.gov.ru/gia/gia-9/",
    },
    "vpr": {"docs": "https://obrnadzor.gov.ru/", "bank": "https://fipi.ru/", "changes": "https://obrnadzor.gov.ru/"},
}


def build_exam_overview_text() -> str:
    return (
        "🎯 <b>Подготовка к экзаменам</b>\n\n"
        "Выбери экзамен, предмет и формат подготовки.\n\n"
        "Что уже работает нормально:\n"
        "• карточки тем\n"
        "• план на сегодня\n"
        "• типичные ошибки 2026\n"
        "• объяснение темы\n"
        "• проверка ответа\n"
        "• мини-вариант\n"
        "• устная часть / сочинение / собеседование\n"
        "• официальные материалы"
    )


def build_subject_topics_text(section: str, subject: str) -> str:
    header = EXAM_DISPLAY_NAMES.get(section, section.upper())
    return f"📚 <b>Карточки тем</b>\n\nРаздел: {header}\nПредмет: {subject}\n\nВыбери тему кнопкой ниже."


def build_official_materials_text(section: str, subject: str | None = None) -> str:
    links = EXAM_SECTION_LINKS[section]
    title = EXAM_DISPLAY_NAMES.get(section, section.upper())
    lines = [f"📂 <b>Официальные материалы {title}</b>", ""]
    if subject:
        lines.extend([f"Предмет: <b>{subject}</b>", ""])
    lines.append(f"• Демоверсии / спецификации / кодификаторы: {links['docs']}")
    lines.append(f"• Открытый банк заданий: {links['bank']}")
    lines.append(f"• Базовый раздел по изменениям: {links['changes']}")
    if section == "ege":
        lines.append(f"• Итоговое сочинение: {links['essay']}")
    if section == "oge":
        lines.append(f"• Итоговое собеседование / ГИА-9: {links['interview']}")
    lines.extend(["", "С чего начать:", "1. Демоверсия", "2. Кодификатор", "3. Открытый банк заданий"])
    return "\n".join(lines)


def get_mode_title(section: str, mode_code: str) -> str:
    for mode in EXAM_MODES.get(section, []):
        if mode.code == mode_code:
            return mode.title
    return mode_code


def get_mode_hint(section: str, mode_code: str) -> str:
    for mode in EXAM_MODES.get(section, []):
        if mode.code == mode_code:
            return mode.prompt_hint
    return "Помоги пользователю понятно и по делу."


def build_mode_intro(section: str, mode_code: str, subject: str | None, class_name: str | None = None) -> str:
    title = get_mode_title(section, mode_code)
    section_name = EXAM_DISPLAY_NAMES.get(section, section.upper())
    subject_part = f"\nПредмет: <b>{subject}</b>" if subject else ""
    class_part = f"\nКласс: <b>{class_name}</b>" if class_name else ""
    if mode_code == "explain":
        action = "Теперь напиши тему, которую нужно объяснить."
    elif mode_code == "check_answer":
        action = "Теперь пришли свой ответ текстом, а для ВПР можно ещё и фото."
    elif mode_code == "mini_test":
        action = "Теперь напиши тему или блок заданий, по которому нужен мини-вариант."
    else:
        action = "Теперь отправь тему, вопрос или задание."
    return f"{title}\n\nРаздел: <b>{section_name}</b>{subject_part}{class_part}\n\n{action}"


def build_exam_prompt(section: str, mode_code: str, user_text: str, subject: str | None = None, class_name: str | None = None) -> tuple[str, str]:
    section_name = EXAM_DISPLAY_NAMES.get(section, section.upper())
    hint = get_mode_hint(section, mode_code)
    subject_line = f"Предмет: {subject}. " if subject else ""
    class_line = f"Класс: {class_name}. " if class_name else ""
    common = (
        f"Ты — сильный и доброжелательный AI-наставник по разделу {section_name}. {subject_line}{class_line}"
        "Пиши на русском языке, понятно, компактно и полезно для Telegram. "
        "Не используй markdown-маркеры вроде ``` или #. "
        f"{hint}"
    )
    if mode_code == "explain":
        system_prompt = common + " Объясняй тему простыми словами, потом дай короткий пример и 1 вопрос для самопроверки."
        prompt = f"Объясни тему простыми словами.\n\n{user_text}"
    elif mode_code == "check_answer":
        system_prompt = common + " Проверь ответ, укажи ошибки, оценку и как улучшить."
        prompt = f"Проверь ответ ученика.\n\n{user_text}"
    elif mode_code == "mini_test":
        system_prompt = common + " Составь мини-вариант из 5 заданий с коротким ключом в конце."
        prompt = f"Сделай мини-вариант по теме.\n\n{user_text}"
    else:
        system_prompt = common
        prompt = user_text
    return prompt, system_prompt


def get_topic_card_text(section: str, subject: str, topic: str) -> str:
    header = EXAM_DISPLAY_NAMES.get(section, section.upper())
    return (
        f"📚 <b>Карточка темы</b>\n\n"
        f"Раздел: {header}\nПредмет: {subject}\nТема: {topic}\n\n"
        f"1. Что это такое\n{topic} — это один из базовых блоков по предмету {subject.lower()}.\n\n"
        "2. Что нужно помнить\n• ключевое правило или идея\n• типовой шаблон решения\n• где чаще всего ошибаются\n\n"
        "3. Мини-пример\nВозьми одно типовое задание по этой теме и проговори решение по шагам.\n\n"
        "4. Самопроверка\nСможешь ли ты объяснить эту тему в 2–3 предложениях без подсказки?"
    )


def get_today_plan_text(section: str, subject: str | None, class_name: str | None = None) -> str:
    header = EXAM_DISPLAY_NAMES.get(section, section.upper())
    title = f"{header} / {subject}" if subject else header
    if class_name:
        title += f" / {class_name}"
    return (
        f"📅 <b>Что учить сегодня</b>\n\n"
        f"Маршрут: {title}\n\n"
        "1. Повтори 1 базовую тему — 20 минут\n"
        "2. Разбери 2 типовые ошибки — 10 минут\n"
        "3. Реши 3 задания по теме — 20 минут\n"
        "4. Проверь себя по 1 вопросу устно — 5 минут\n"
        "5. Вечером быстро повтори формулы/правила — 10 минут\n\n"
        "Фокус дня: не гонись за объёмом, лучше 1 тема, но до понимания."
    )


def get_common_mistakes_text(section: str, subject: str | None) -> str:
    header = EXAM_DISPLAY_NAMES.get(section, section.upper())
    subject_line = f"\nПредмет: {subject}" if subject else ""
    return (
        f"⚠️ <b>Типичные ошибки 2026</b>\n\nРаздел: {header}{subject_line}\n\n"
        "1. Невнимательно читают условие\n"
        "2. Теряют знак, единицы или ограничение\n"
        "3. Не доводят решение до финального ответа\n"
        "4. Путают формулировку критерия и фактический ответ\n"
        "5. Не проверяют себя на очевидные ошибки\n\n"
        "Как избежать:\n• всегда перечитывай условие\n• выделяй, что нужно найти\n• делай мини-проверку в конце"
    )


def get_speaking_simulator_text(section: str, subject: str | None) -> str:
    kind = "итогового собеседования" if section == "oge" else "устной части"
    return (
        f"🎙 <b>Мини-симулятор {kind}</b>\n\n"
        "Что делать:\n"
        "1. Возьми 1 тему и ответь на неё вслух 60–90 секунд.\n"
        "2. Следи за структурой: тезис → пример → вывод.\n"
        "3. После ответа проверь: логика, точность, уверенность.\n\n"
        "Шаблон сильного ответа:\n"
        "• сначала коротко сформулируй мысль\n"
        "• затем приведи 1–2 аргумента\n"
        "• закончи коротким выводом"
    )


def get_final_essay_text(section: str, subject: str | None) -> str:
    return (
        "✍️ <b>Итоговое сочинение</b>\n\n"
        "Структура:\n"
        "1. Вступление и тезис\n"
        "2. Первый аргумент\n"
        "3. Второй аргумент\n"
        "4. Вывод\n\n"
        "Что важно:\n"
        "• не уходить от темы\n"
        "• формулировать позицию ясно\n"
        "• использовать понятные аргументы\n"
        "• завершать логичным выводом"
    )


def get_final_interview_text(section: str, subject: str | None) -> str:
    return (
        "🗣 <b>Итоговое собеседование</b>\n\n"
        "Основные части:\n"
        "1. Чтение текста\n"
        "2. Пересказ\n"
        "3. Монолог\n"
        "4. Диалог\n\n"
        "Как тренироваться:\n"
        "• отвечай кратко, но полно\n"
        "• не бойся простых формулировок\n"
        "• держи структуру ответа\n"
        "• потренируйся говорить вслух по таймеру"
    )
