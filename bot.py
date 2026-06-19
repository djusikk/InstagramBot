import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)
import anthropic

# ============================
# КЛЮЧІ — вставляти в Railway Environment Variables
# ============================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

# ============================
# СТАНИ РОЗМОВИ
# ============================
CHOOSING_TYPE, WAITING_PRODUCT = range(2)

# ============================
# ТИПИ ОПИСІВ
# ============================
DESCRIPTION_TYPES = {
    "selling": {
        "label": "🔥 Продаючий (макс. конверсія)",
        "prompt": """Ти топовий копірайтер для Instagram-магазинів. Напиши продаючий опис товару українською мовою.

СТРУКТУРА (дотримуйся чітко):
1. 🔥 ГАЧОК (1 речення — біль або мрія аудиторії)
2. 💎 ЩО ЦЕ (коротко, 1-2 речення)
3. ✅ ОФФЕР — 3-4 конкретні вигоди для покупця (не характеристики!)
4. ⚡ ТРИГЕР ТЕРМІНОВОСТІ (обмеження часу/кількості)
5. 📦 УМОВИ (доставка, оплата, гарантія — коротко)
6. 👇 ЗАКЛИК ДО ДІЇ (конкретний CTA)
7. Хештеги (5-7 релевантних)

ПРАВИЛА:
- Мова: українська, жива, без канцеляризму
- Не пиши "якісний", "чудовий", "унікальний" — це порожні слова
- Звертайся до читача на "ти"
- Емодзі помірно — лише там де підсилюють
- Розмір: 150-220 слів"""
    },
    "story": {
        "label": "📖 Сторітелінг (через емоцію)",
        "prompt": """Ти копірайтер для Instagram. Напиши опис товару через сторітелінг — українською мовою.

СТРУКТУРА:
1. Почни з короткої історії або ситуації (з якою впізнає себе читач)
2. Покажи як товар вирішує цю ситуацію
3. 3 ключові переваги через відчуття/результат
4. М'який заклик до дії
5. Хештеги (5-7)

ПРАВИЛА:
- Емоційно, живо, як розмова з другом
- Звертайся на "ти"
- Без шаблонних фраз
- 130-180 слів"""
    },
    "minimal": {
        "label": "✨ Мінімалістичний (преміум стиль)",
        "prompt": """Ти копірайтер для преміум Instagram-акаунтів. Напиши лаконічний опис товару — українською.

СТРУКТУРА:
1. Одне сильне речення-заголовок
2. 3 коротких пункти (по 1 речення) — суть, вигода, відчуття
3. Умови + CTA (1-2 речення)
4. Хештеги (3-5, нішеві)

ПРАВИЛА:
- Стиль: чистий, впевнений, без зайвих слів
- Ніяких оклику або агресивних продажів
- Максимум 100 слів"""
    },
    "review": {
        "label": "💬 Від імені покупця (соціальний доказ)",
        "prompt": """Ти копірайтер для Instagram. Напиши опис товару у форматі відгуку реального покупця — українською.

СТРУКТУРА:
1. Початок від першої особи (ситуація до покупки)
2. Враження від товару (конкретно, не загально)
3. Результат / зміна
4. Рекомендація + CTA від магазину
5. Хештеги (5-7)

ПРАВИЛА:
- Звучить як справжній відгук, не реклама
- Конкретні деталі (скільки часу, що змінилось)
- 120-160 слів"""
    }
}

SYSTEM_PROMPT = """Ти провідний копірайтер для українських Instagram-магазинів.
Твої описи: продають, звучать живо, мотивують до дії.
Відповідай ТІЛЬКИ готовим описом — без вступних слів, без пояснень, без коментарів."""

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def generate_description(product_info: str, desc_type: str) -> str:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    type_config = DESCRIPTION_TYPES[desc_type]
    user_prompt = f"{type_config['prompt']}\n\nТОВАР:\n{product_info}"

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return message.content[0].text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton(v["label"], callback_data=k)]
        for k, v in DESCRIPTION_TYPES.items()
    ]
    await update.message.reply_text(
        "👋 Привіт! Я генерую продаючі описи для Instagram.\n\n"
        "Обери стиль опису:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_TYPE


async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["desc_type"] = query.data
    chosen = DESCRIPTION_TYPES[query.data]["label"]

    await query.edit_message_text(
        f"✅ Обрано: {chosen}\n\n"
        "Тепер опиши товар:\n\n"
        "📝 Що написати:\n"
        "• Назва товару\n"
        "• Для кого / яка проблема вирішується\n"
        "• Ключові характеристики\n"
        "• Ціна (опціонально)\n\n"
        "Пиши довільно — я розберусь 👇"
    )
    return WAITING_PRODUCT


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    product_info = update.message.text
    desc_type = context.user_data.get("desc_type", "selling")

    thinking_msg = await update.message.reply_text("⏳ Генерую опис...")

    try:
        description = generate_description(product_info, desc_type)
        await thinking_msg.delete()

        keyboard = [
            [
                InlineKeyboardButton("🔄 Ще варіант", callback_data=f"regen_{desc_type}"),
                InlineKeyboardButton("🎨 Інший стиль", callback_data="new_type")
            ],
            [InlineKeyboardButton("📝 Новий товар", callback_data="new_product")]
        ]

        await update.message.reply_text(
            f"✅ Готово! ({DESCRIPTION_TYPES[desc_type]['label']})\n\n"
            f"{'─' * 30}\n\n"
            f"{description}\n\n"
            f"{'─' * 30}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data["last_product"] = product_info

    except Exception as e:
        logger.error(f"Помилка генерації: {e}")
        await thinking_msg.edit_text("❌ Помилка при генерації. Спробуй ще раз /start")

    return ConversationHandler.END


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("regen_"):
        desc_type = data.replace("regen_", "")
        product_info = context.user_data.get("last_product", "")

        if not product_info:
            await query.edit_message_text("Почни знову: /start")
            return ConversationHandler.END

        await query.edit_message_text("⏳ Генерую новий варіант...")

        try:
            description = generate_description(product_info, desc_type)
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Ще варіант", callback_data=f"regen_{desc_type}"),
                    InlineKeyboardButton("🎨 Інший стиль", callback_data="new_type")
                ],
                [InlineKeyboardButton("📝 Новий товар", callback_data="new_product")]
            ]
            await query.edit_message_text(
                f"✅ Новий варіант! ({DESCRIPTION_TYPES[desc_type]['label']})\n\n"
                f"{'─' * 30}\n\n"
                f"{description}\n\n"
                f"{'─' * 30}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Помилка: {e}")
            await query.edit_message_text("❌ Помилка. Спробуй /start")

        return ConversationHandler.END

    elif data in ("new_type", "new_product"):
        keyboard = [
            [InlineKeyboardButton(v["label"], callback_data=k)]
            for k, v in DESCRIPTION_TYPES.items()
        ]
        text = "Обери стиль:" if data == "new_type" else "Новий товар! Обери стиль:"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return CHOOSING_TYPE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано. Натисни /start щоб почати знову.")
    return ConversationHandler.END


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(button_callback, pattern="^new_product$")
        ],
        states={
            CHOOSING_TYPE: [
                CallbackQueryHandler(choose_type, pattern="^(selling|story|minimal|review)$"),
                CallbackQueryHandler(button_callback, pattern="^new_type$")
            ],
            WAITING_PRODUCT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, generate)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(button_callback, pattern="^(regen_.*|new_type|new_product)$")
        ],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    logger.info("Бот запущено!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
