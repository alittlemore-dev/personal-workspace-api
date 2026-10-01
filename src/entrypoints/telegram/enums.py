from core.enums import TranslationStrEnum


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
        "Форма устарела. Начните заново: /finance.",
        "This form has expired. Start again: /finance.",
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
