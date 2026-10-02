from core.enums import StrEnum, TranslationStrEnum


class TelegramNavigationAction(StrEnum):
    MENU = "menu"
    FINANCE = "finance"
    HELP = "help"
    CANCEL = "cancel"
    UNKNOWN = "unknown"


class TelegramNavigationText(TranslationStrEnum):
    FINANCE = ("finance", "Финансы", "Finance")
    HELP = ("help", "Помощь", "Help")
    CANCEL = ("cancel", "Отмена", "Cancel")
    MENU = (
        "menu",
        "Добро пожаловать в Personal Workspace. Выберите действие кнопками ниже.",
        "Welcome to Personal Workspace. Choose an action using the buttons below.",
    )
    FINANCE_ENTRY = (
        "finance_entry",
        "Финансы: добавьте операцию или продолжите текущую. «Отмена» сбросит её.",
        "Finance: continue your current transaction or start a new one. Use Cancel to discard it.",
    )
    HELP_MESSAGE = (
        "help_message",
        (
            "«Финансы» — добавить доход или расход либо продолжить незавершённую операцию. "
            "«Отмена» — отменить операцию. Выборы доступны кнопками под сообщениями. "
            "Сумму, описание и другую дату вводите обычным текстом. "
            "Для подключения откройте приглашение владельца Workspace и дождитесь подтверждения. "
            "Команды тоже доступны: /start, /menu, /finance, /help, /cancel."
        ),
        (
            "Finance adds income or expenses, or resumes your unfinished transaction. "
            "Cancel discards the transaction. Use the buttons below messages to select options. "
            "Enter amounts, descriptions and custom dates as plain text. "
            "To connect, open the Workspace owner's invitation and wait for approval. "
            "Commands are also available: /start, /menu, /finance, /help, /cancel."
        ),
    )
    NOTHING_TO_CANCEL = (
        "nothing_to_cancel",
        "Нет незавершённой операции. Выберите действие кнопками ниже.",
        "There is no unfinished transaction. Choose an action using the buttons below.",
    )
    UNKNOWN = (
        "unknown",
        "Выберите действие кнопками ниже. «Финансы» также продолжит незавершённую операцию.",
        "Choose an action using the buttons below. Finance also resumes an unfinished transaction.",
    )
    ACCESS = (
        "access",
        "Для доступа откройте приглашение владельца Workspace и дождитесь подтверждения.",
        "To access the bot, open the Workspace owner's invitation and wait for approval.",
    )
    RETRY = (
        "retry",
        "Бот временно недоступен. Попробуйте позже.",
        "The bot is temporarily unavailable. Try again later.",
    )


class FinanceConversationText(TranslationStrEnum):
    START = (
        "start",
        "Добавить операцию: выберите доход или расход.",
        "Add a transaction: choose income or expense.",
    )
    CATEGORY = (
        "category",
        "Выберите категорию.",
        "Choose a category.",
    )
    AMOUNT = (
        "amount",
        "Введите положительную сумму.",
        "Enter a positive amount.",
    )
    CURRENCY = (
        "currency",
        "Выберите валюту.",
        "Choose a currency.",
    )
    DATE = (
        "date",
        "Выберите время операции.",
        "Choose the transaction time.",
    )
    NOW = (
        "now",
        "Сейчас",
        "Now",
    )
    CUSTOM = (
        "custom",
        "Другая дата",
        "Another date",
    )
    DATE_INPUT = (
        "date_input",
        "Введите ДД.ММ.ГГГГ ЧЧ:ММ в часовом поясе {zone}. Только текущий месяц.",
        "Enter DD.MM.YYYY HH:MM in {zone}. Current month only.",
    )
    DESCRIPTION = (
        "description",
        "Введите описание или пропустите этот шаг.",
        "Enter a description or skip this step.",
    )
    SKIP = (
        "skip",
        "Пропустить",
        "Skip",
    )
    CONFIRM = (
        "confirm",
        "Подтвердить",
        "Confirm",
    )
    BACK = (
        "back",
        "Назад",
        "Back",
    )
    CANCEL = (
        "cancel",
        "Отмена",
        "Cancel",
    )
    CANCELED = (
        "canceled",
        "Добавление отменено.",
        "Transaction entry canceled.",
    )
    SAVED = (
        "saved",
        "Операция сохранена.",
        "Transaction saved.",
    )
    STALE = (
        "stale",
        "Форма устарела. Нажмите «Финансы», чтобы продолжить или начать заново.",
        "This form has expired. Press Finance to continue or start again.",
    )
    INVALID = (
        "invalid",
        "Проверьте введённое значение и повторите попытку.",
        "Check the entered value and try again.",
    )
    ACCESS = (
        "access",
        "Доступ недоступен. Обратитесь к владельцу Workspace.",
        "Access is unavailable. Contact the Workspace owner.",
    )
    INITIALIZE = (
        "initialize",
        "Сначала откройте финансовый трекер на сайте для его настройки.",
        "First open the finance tracker on the website to initialize it.",
    )
    RETRY = (
        "retry",
        "Не удалось сохранить. Повторите подтверждение позже.",
        "Unable to save. Retry confirmation later.",
    )
    EMPTY = (
        "empty",
        "Нет доступных категорий. Настройте их на сайте.",
        "No available categories. Configure them on the website.",
    )
    NEXT = (
        "next",
        "Далее",
        "Next",
    )
    PREVIOUS = (
        "previous",
        "Предыдущие",
        "Previous",
    )
