from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExamMode:
    code: str
    title: str
    prompt_hint: str


EXAM_ROOT_BUTTON = "🎯 Подготовка ЕГЭ / ОГЭ / ВПР"

EXAM_SECTIONS = {
    "ege": "ЕГЭ",
    "oge": "ОГЭ",
    "vpr": "ВПР",
}

EXAM_DISPLAY_NAMES = {
    "ege": "ЕГЭ",
    "oge": "ОГЭ",
    "vpr": "ВПР",
}

EXAM_SECTION_LINKS = {
    "ege": {
        "main": "https://fipi.ru/ege",
        "docs": "https://fipi.ru/ege/demoversii-specifikacii-kodifikatory",
        "bank": "https://ege.fipi.ru/bank/",
        "changes": "https://doc.fipi.ru/ege/demoversii-specifikacii-kodifikatory/2026/Izmeneniya_KIM_EGE_2026.pdf",
        "essay": "https://obrnadzor.gov.ru/gia/gia-11/itogovoe-sochinenie-izlozhenie/",
    },
    "oge": {
        "main": "https://fipi.ru/oge",
        "docs": "https://fipi.ru/oge/demoversii-specifikacii-kodifikatory",
        "bank": "https://oge.fipi.ru/bank/index.php",
        "changes": "https://doc.fipi.ru/oge/demoversii-specifikacii-kodifikatory/2026/Izmeneniya_KIM_OGE_2026.pdf",
        "interview": "https://fipi.ru/oge/demoversii-specifikacii-kodifikatory#!/tab/173801626-2",
        "gia9": "https://obrnadzor.gov.ru/gia/gia-9/kak-uchastvovat-v-gia-9/",
    },
    "vpr": {
        "main": "https://obrnadzor.gov.ru/gia/",
        "docs": "https://obrnadzor.gov.ru/",
        "bank": "https://fipi.ru/",
        "changes": "https://obrnadzor.gov.ru/",
    },
}

EXAM_SUBJECTS = {
    "ege": [
        "Русский язык",
        "Математика",
        "Обществознание",
        "Информатика",
        "Биология",
        "История",
        "Английский язык",
        "Физика",
        "Химия",
        "Литература",
        "География",
    ],
    "oge": [
        "Русский язык",
        "Математика",
        "Обществознание",
        "Информатика",
        "Биология",
        "История",
        "Английский язык",
        "Физика",
        "Химия",
        "Литература",
        "География",
    ],
    "vpr": [
        "Русский язык",
        "Математика",
        "Окружающий мир",
        "История",
        "Биология",
        "География",
        "Обществознание",
        "Физика",
    ],
}

VPR_CLASSES = ["4 класс", "5 класс", "6 класс", "7 класс", "8 класс", "10 класс"]

EXAM_MODES: dict[str, list[ExamMode]] = {
    "ege": [
        ExamMode("subject_cards", "📚 Карточки тем", "Сделай 8 кратких карточек по теме с ключевыми формулами, идеями и антиошибками."),
        ExamMode("daily_plan", "📅 Что учить сегодня", "Составь реалистичный план на сегодня с блоками 25–40 минут, приоритетами и короткой самопроверкой."),
        ExamMode("typical_errors", "⚠️ Типичные ошибки 2026", "Покажи самые типичные ошибки учеников и как их избежать в стиле ФИПИ."),
        ExamMode("mini_test", "🧪 Вариант на сегодня", "Собери мини-вариант на сегодня: 5 заданий разного уровня и краткий ключ после ответа пользователя."),
        ExamMode("explain", "📖 Объяснить тему", "Объясни тему простыми словами, потом дай 3 мини-примера и 1 проверочный вопрос."),
        ExamMode("check_answer", "📝 Проверить ответ", "Проверь ответ по критериям ЕГЭ, оцени слабые места и покажи улучшенную версию."),
        ExamMode("speaking", "🎙 Мини-симулятор устной части", "Проведи краткий симулятор устной части: дай задание, критерии и модель сильного ответа."),
        ExamMode("essay", "✍️ Итоговое сочинение", "Помоги с итоговым сочинением: тема, тезис, аргументы, план, каркас и типичные ошибки."),
        ExamMode("official", "📂 Официальные материалы", "Покажи, какие официальные материалы открыть по этому предмету и что из них взять в первую очередь."),
    ],
    "oge": [
        ExamMode("subject_cards", "📚 Карточки тем", "Сделай 8 понятных карточек по теме для 9 класса: правило, пример, антиошибка, мини-проверка."),
        ExamMode("daily_plan", "📅 Что учить сегодня", "Составь план подготовки на сегодня по ОГЭ с акцентом на слабые темы и 1 мини-тестом в конце."),
        ExamMode("typical_errors", "⚠️ Типичные ошибки 2026", "Покажи типичные ошибки участников ОГЭ и как их избежать понятным языком."),
        ExamMode("mini_test", "🧪 Мини-вариант", "Собери мини-вариант ОГЭ: 5 заданий с коротким разбором после выполнения."),
        ExamMode("explain", "📖 Объяснить тему", "Объясни тему как для 9 класса: просто, по шагам, с мини-практикой."),
        ExamMode("check_answer", "📝 Проверить ответ", "Проверь ответ по логике ОГЭ, укажи ошибки и покажи, как поднять балл."),
        ExamMode("speaking", "🎙 Мини-симулятор устной части", "Проведи симулятор устной части или устного ответа с критериями и моделью."),
        ExamMode("interview", "🗣 Итоговое собеседование", "Помоги подготовиться к итоговому собеседованию: структура, речь, шаблон ответа и типичные ошибки."),
        ExamMode("official", "📂 Официальные материалы", "Покажи, какие официальные материалы ОГЭ по предмету открыть и что в них смотреть первым делом."),
    ],
    "vpr": [
        ExamMode("subject_cards", "📚 Карточки тем", "Сделай короткие карточки по теме для школьной подготовки: правило, пример, мини-вопрос."),
        ExamMode("daily_plan", "📅 Что учить сегодня", "Составь лёгкий план на сегодня для подготовки к ВПР: 3 блока, 1 повторение, 1 мини-тест."),
        ExamMode("typical_errors", "⚠️ Типичные ошибки", "Покажи частые ошибки школьников по этой теме и как их быстро исправить."),
        ExamMode("mini_test", "🧪 Мини-тест", "Собери короткий школьный мини-тест из 5 заданий с понятным разбором."),
        ExamMode("explain", "📖 Объяснить тему", "Объясни тему очень просто, как на уроке: 3 шага, 2 примера и мини-проверка."),
        ExamMode("check_answer", "📝 Проверить ответ", "Проверь ответ школьника, покажи ошибки и перепиши правильный вариант."),
        ExamMode("photo", "📷 Разбор по фото", "Разбери задание по фото: распознай условие, объясни и дай ответ понятным языком."),
        ExamMode("review", "⚡ Повторение за 5 минут", "Сделай суперкороткое повторение темы за 5 минут: только самое важное."),
        ExamMode("official", "📂 Полезные материалы", "Покажи полезные официальные и открытые материалы для школьной подготовки без пиратских источников."),
    ],
}

TOPICS = {
    ("ege", "Русский язык"): ["Н/НН", "Пунктуация в сложных предложениях", "Сочинение ЕГЭ", "Средства выразительности", "Орфоэпия", "Паронимы"],
    ("ege", "Математика"): ["Логарифмы", "Производная", "Тригонометрия", "Стереометрия", "Вероятность", "Параметры"],
    ("ege", "Обществознание"): ["Политика", "Экономика", "Право", "Социальные отношения", "Человек и общество", "Конституция РФ"],
    ("ege", "Информатика"): ["Циклы", "Массивы", "Рекурсия", "Системы счисления", "Таблицы истинности", "Файлы и строки"],
    ("oge", "Русский язык"): ["Изложение", "Сочинение 13.3", "Орфография", "Пунктуация", "Грамматическая основа", "Средства выразительности"],
    ("oge", "Математика"): ["Уравнения", "Неравенства", "Геометрия", "Графики функций", "Вероятность", "Текстовые задачи"],
    ("oge", "Обществознание"): ["Человек", "Общество", "Экономика", "Право", "Политика", "Социальная сфера"],
    ("oge", "Информатика"): ["Алгоритмы", "Исполнители", "Логика", "Таблицы", "Кодирование", "Программирование"],
    ("vpr", "Русский язык"): ["Орфограммы", "Главные члены предложения", "Пунктуация", "Текст и тема", "Части речи", "Разбор слова"],
    ("vpr", "Математика"): ["Дроби", "Уравнения", "Проценты", "Задачи на движение", "Площадь и периметр", "Графики"],
}


def build_exam_overview_text() -> str:
    return (
        "🎯 <b>Подготовка ЕГЭ / ОГЭ / ВПР</b>\n\n"
        "Здесь можно выбрать экзамен, предмет и формат подготовки.\n\n"
        "Что доступно:\n"
        "• карточки тем\n"
        "• что учить сегодня\n"
        "• типичные ошибки 2026\n"
        "• мини-варианты и мини-тесты\n"
        "• объяснение тем\n"
        "• проверка ответов\n"
        "• мини-симулятор устной части\n"
        "• итоговое сочинение / итоговое собеседование\n"
        "• ссылки на официальные материалы"
    )


def build_subject_topics_text(section: str, subject: str) -> str:
    topics = TOPICS.get((section, subject), [
        "Ключевые темы предмета",
        "Типовые задания",
        "Ошибки и ловушки",
        "Быстрое повторение",
        "Проверка ответа",
        "Тренировка на сегодня",
    ])
    header = EXAM_DISPLAY_NAMES.get(section, section.upper())
    lines = [f"📚 <b>{header}: {subject}</b>", "", "Подборка тем для старта:"]
    for item in topics[:8]:
        lines.append(f"• {item}")
    lines.append("")
    lines.append("Выбери режим ниже или просто напиши тему своим сообщением.")
    return "\n".join(lines)


def build_official_materials_text(section: str, subject: str | None = None) -> str:
    links = EXAM_SECTION_LINKS[section]
    title = EXAM_DISPLAY_NAMES.get(section, section.upper())
    suffix = f" по предмету <b>{subject}</b>" if subject else ""
    lines = [f"📂 <b>Официальные материалы {title}{suffix}</b>", ""]
    if section in {"ege", "oge"}:
        lines.extend([
            f"• Демоверсии / спецификации / кодификаторы: {links['docs']}",
            f"• Открытый банк заданий: {links['bank']}",
            f"• Изменения в КИМ 2026: {links['changes']}",
        ])
    else:
        lines.extend([
            f"• Раздел Рособрнадзора: {links['main']}",
            f"• ФИПИ: {links['bank']}",
        ])

    if section == "ege":
        lines.append(f"• Итоговое сочинение: {links['essay']}")
    if section == "oge":
        lines.append(f"• Как участвовать в ГИА-9: {links['gia9']}")
        lines.append(f"• Материалы по итоговому собеседованию: {links['interview']}")

    lines.extend([
        "",
        "Что открыть в первую очередь:",
        "1. изменения 2026;",
        "2. демоверсию;",
        "3. кодификатор тем;",
        "4. открытый банк заданий.",
    ])
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
    return "Помоги пользователю по теме экзамена понятно, полезно и по делу."


def build_mode_intro(section: str, mode_code: str, subject: str | None, class_name: str | None = None) -> str:
    title = get_mode_title(section, mode_code)
    section_name = EXAM_DISPLAY_NAMES.get(section, section.upper())
    subject_part = f"\nПредмет: <b>{subject}</b>" if subject else ""
    class_part = f"\nКласс: <b>{class_name}</b>" if class_name else ""
    return (
        f"{title}\n\n"
        f"Раздел: <b>{section_name}</b>{subject_part}{class_part}\n\n"
        "Теперь отправь тему, вопрос, ответ или задание.\n"
        "Можно прислать текст, а для ВПР в режиме по фото — ещё и изображение."
    )


def build_exam_prompt(section: str, mode_code: str, user_text: str, subject: str | None = None, class_name: str | None = None) -> tuple[str, str]:
    section_name = EXAM_DISPLAY_NAMES.get(section, section.upper())
    hint = get_mode_hint(section, mode_code)
    subject_line = f"Предмет: {subject}. " if subject else ""
    class_line = f"Класс: {class_name}. " if class_name else ""

    common = (
        f"Ты — сильный и доброжелательный AI-наставник по разделу {section_name}. "
        f"{subject_line}{class_line}"
        "Пиши на русском языке. Отвечай понятно, компактно и полезно для Telegram. "
        "Не используй markdown-маркеры вроде ``` или #. Можно использовать обычный текст, короткие абзацы и нумерацию. "
        "Не выдумывай официальные нормы или точные критерии, если они не указаны пользователем. "
        f"{hint}"
    )

    if mode_code == "subject_cards":
        system_prompt = common + " Сформируй карточки тем: термин, краткое объяснение, пример, антиошибка, мини-вопрос."
        prompt = f"Сделай карточки тем для подготовки.\n\n{user_text}"
    elif mode_code == "daily_plan":
        system_prompt = common + " Составь реалистичный план на сегодня: 3–5 блоков, что делать по порядку, что повторить вечером."
        prompt = f"Составь план, что учить сегодня.\n\n{user_text}"
    elif mode_code == "typical_errors":
        system_prompt = common + " Покажи типичные ошибки, ловушки, как их заметить и как избежать."
        prompt = f"Покажи типичные ошибки 2026 по теме.\n\n{user_text}"
    elif mode_code in {"mini_test", "review"}:
        system_prompt = common + " Дай короткий тренировочный формат: задания или суперкороткое повторение, затем краткий ключ или чек-лист."
        prompt = f"Сделай тренировочный материал.\n\n{user_text}"
    elif mode_code == "explain":
        system_prompt = common + " Объясняй тему простыми словами, шаг за шагом, с примерами и мини-проверкой в конце."
        prompt = f"Объясни тему.\n\n{user_text}"
    elif mode_code == "check_answer":
        system_prompt = common + " Проверь ответ, оцени сильные и слабые места, затем покажи улучшенную версию."
        prompt = f"Проверь ответ ученика.\n\n{user_text}"
    elif mode_code == "speaking":
        system_prompt = common + " Проведи мини-симулятор устной части: формат задания, на что смотреть, модель сильного ответа и 3 совета."
        prompt = f"Проведи мини-симулятор устной части.\n\n{user_text}"
    elif mode_code == "essay":
        system_prompt = common + " Помоги с итоговым сочинением: тезис, аргументы, план, каркас, частые ошибки и как их избежать."
        prompt = f"Помоги подготовиться к итоговому сочинению.\n\n{user_text}"
    elif mode_code == "interview":
        system_prompt = common + " Помоги подготовиться к итоговому собеседованию: структура ответа, речь, шаблон и типичные ошибки."
        prompt = f"Помоги подготовиться к итоговому собеседованию.\n\n{user_text}"
    else:
        system_prompt = common
        prompt = user_text

    return prompt, system_prompt
