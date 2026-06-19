import os
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)
import anthropic

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

CHOOSING_TYPE, WAITING_PRODUCT = range(2)

DESCRIPTION_TYPES = {
    "selling": {
        "label": "🔥 Продаючий (макс. конверсія)",
        "prompt": """Ти топовий копірайтер для Instagram-магазинів. Напиши продаючий опис товару українською мовою.

СТРУКТУРА:
1. ГАЧОК (1 речення — біль або мрія аудиторії)
2. ЩО ЦЕ (коротко, 1-2 речення)
3. ОФФЕР — 3-4 конкретні вигоди для покупця
4. ТРИГЕР ТЕРМІНОВОСТІ
5. УМОВИ (доставка, оплата, гарантія)
6. ЗАКЛИК ДО ДІЇ
7. Хештеги (5-7)

ПРАВИЛА: українська жива мова, звертайся на "ти", 150-220 слів
ВАЖЛИВО: НЕ використовуй символи * ** # для форматування. Тільки емодзі і звичайний текст."""
    },
    "story": {
        "label": "📖 Сторітелінг (через емоцію)",
        "prompt": """Напиши опис товару через сторітелінг українською мовою.

СТРУКТУРА:
1. Коротка історія/ситуація з якою впізнає себе читач
2. Як товар вирішує цю ситуацію
3. 3 ключові переваги через відчуття
4. М'який заклик до дії
5. Хештеги (5-7)

ПРАВИЛА: емоційно, живо, звертайся на "ти", 130-180 слів
ВАЖЛИВО: НЕ використовуй символи * ** # для форматування. Тільки емодзі і звичайний текст."""
    },
    "minimal": {
        "label": "✨ Мінімалістичний (преміум)",
        "prompt": """Напиши лаконічний преміум опис товару українською.

СТРУКТУРА:
1. Одне сильне речення-заголовок
2. 3 коротких пункти — суть, вигода, відчуття
3. Умови + CTA
4. Хештеги (3-5)

ПРАВИЛА: чистий впевнений стиль, максимум 100 слів
ВАЖЛИВО: НЕ використовуй символи * ** # для форматування. Тільки емодзі і звичайний текст."""
    },
    "review": {
        "label": "💬 Від покупця (соціальний доказ)",
        "prompt": """Напиши опис товару у форматі відгуку реального покупця українською.

СТРУКТУРА:
1. Від першої особи (ситуація до покупки)
2. Враження від товару конкретно
3. Результат/зміна
4. Рекомендація + CTA
5. Хештеги (5-7)

ПРАВИЛА: звучить як справжній відгук, 120-160 слів
ВАЖЛИВО: НЕ використовуй символи * ** # для форматування. Тільки емодзі і звичайний текст."""
    }
}

SYSTEM_PROMPT = """Ти провідний копірайтер для українських Instagram-магазинів.
Відповідай ТІЛЬКИ готовим описом — без вступних слів і пояснень.
НІКОЛИ не використовуй * ** # markdown символи. Тільки звичайний текст і емодзі."""

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Видаляє markdown символи з тексту"""
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'#+\s?', '', text)
    text = re.sub(r'_{2,}', '', text)
    return text.strip()


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
    return clean_text(message.content[0].text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[InlineKeyboardButton(v["label"], callback_data=k)] for k, v in DESCRIPTION_TYPES.items()]
    await update.message.reply_text(
        "👋 Привіт! Я генерую продаючі описи для Instagram.\n\nОбери стиль опису:",
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
        "• Назва товару\n"
        "• Для кого / яка проблема\n"
        "• Ключові характеристики\n"
        "• Ціна (опціонально)\n\n"
        "Пиши довільно 👇"
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

        # Відправляємо опис у monospace блоці для легкого копіювання
        await update.message.reply_text(
            f"✅ Готово! ({DESCRIPTION_TYPES[desc_type]['label']})\n\n"
            f"`{description}`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="MarkdownV2"
        )
        context.user_data["last_product"] = product_info
        context.user_data["last_type"] = desc_type
    except Exception as e:
        logger.error(f"Помилка: {e}")
        await thinking_msg.edit_text("❌ Помилка. Спробуй /start")
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
                f"`{description}`",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="MarkdownV2"
            )
        except Exception as e:
            logger.error(f"Помилка: {e}")
            await query.edit_message_text("❌ Помилка. Спробуй /start")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(v["label"], callback_data=k)] for k, v in DESCRIPTION_TYPES.items()]
    text = "Обери стиль:" if data == "new_type" else "Новий товар! Обери стиль:"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_TYPE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано. Натисни /start")
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
        allow_reentry=True,
        conversation_timeout=600  # 10 хвилин таймаут
    )
    app.add_handler(conv_handler)
    # Обробник кнопок поза розмовою (для старих повідомлень)
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(regen_.*|new_type|new_product)$"))
    logger.info("Бот запущено!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
