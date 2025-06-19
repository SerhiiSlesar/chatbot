from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from datetime import datetime
from fpdf import FPDF
import os
import json
from dotenv import load_dotenv

# Conversation states
(ASK_NAME, ASK_ADDRESS, ASK_DATE, COLLECT_WORK, CONFIRMATION) = range(5)

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GPT_API_KEY = os.getenv("OPENROUTER_API_KEY")


# Default work types and prices
WORK_PRICES = {
    "Підрозетники (вибурювання)": 80,
    "Підрозетники (установка з гіпсом)": 50,
    "Штроблення (бетон)": 100,
    "Замазування штроби": 30,
    "Прокладка кабелю": 33,
    "Розподільча коробка (установка)": 100,
    "Розподільча коробка (розпайка)": 150,
    "Автомат (установка і розключення)": 100,
    "Щит (ніша, 48 модулів)": 800,
}

# Materials linked to works
MATERIALS = {
    "Гіпс (5 кг на 15 підрозетників)": {
        "related_to": "Підрозетники (установка з гіпсом)",
        "rate": 5 / 15,
        "price_per_kg": 20,
    },
    "Кабель ВВГнг (пог.м)": {
        "related_to": "Прокладка кабелю",
        "rate": 1,
        "price_per_m": 35,
    },
}

AUTHORIZED_USERS = [123456789]  # replace with your user_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("⛔️ Доступ заборонено. Зверніться до адміністратора.")
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text(
        "Вітаю! Давайте створимо акт виконаних робіт.\n\nЯк звати замовника?"
    )
    return ASK_NAME


async def ask_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("Вкажіть адресу виконання робіт:")
    return ASK_ADDRESS


async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["address"] = update.message.text
    keyboard = [["Сьогодні", "Ввести вручну"]]
    await update.message.reply_text(
        "Вкажіть дату виконання робіт:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return ASK_DATE


async def collect_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "Сьогодні":
        context.user_data["date"] = datetime.now().strftime("%d.%m.%Y")
    else:
        context.user_data["date"] = text
    context.user_data["works"] = {}
    keyboard = [[InlineKeyboardButton(w, callback_data=w)] for w in WORK_PRICES]
    await update.message.reply_text(
        "Оберіть види робіт (по одному):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return COLLECT_WORK


async def collect_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    work_type = query.data
    context.user_data["current_work"] = work_type
    await query.message.reply_text(f"Скільки одиниць роботи: '{work_type}'?")
    return CONFIRMATION


async def save_work_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qty = update.message.text
    if not qty.isdigit():
        await update.message.reply_text("Введіть кількість цифрою.")
        return CONFIRMATION

    work = context.user_data.get("current_work")
    context.user_data["works"][work] = int(qty)

    keyboard = [[InlineKeyboardButton(w, callback_data=w)] for w in WORK_PRICES]
    keyboard.append([InlineKeyboardButton("✅ Завершити", callback_data="done")])
    await update.message.reply_text(
        "Оберіть наступний вид роботи або завершіть:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return COLLECT_WORK


async def finish_collection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    summary = "🧾 Акт виконаних робіт\n"
    summary += f"Дата: {context.user_data['date']}\n"
    summary += f"Замовник: {context.user_data['name']}\n"
    summary += f"Адреса: {context.user_data['address']}\n\n"

    total = 0
    for w, q in context.user_data["works"].items():
        price = WORK_PRICES[w]
        cost = price * q
        total += cost
        summary += f"{w}: {q} × {price} = {cost} грн\n"

    summary += "\n📦 Матеріали:\n"
    materials_cost = 0
    for mat, props in MATERIALS.items():
        work_key = props["related_to"]
        if work_key in context.user_data["works"]:
            qty = context.user_data["works"][work_key] * props["rate"]
            if "price_per_kg" in props:
                cost = round(qty * props["price_per_kg"])
                summary += f"{mat}: {qty:.1f} кг × {props['price_per_kg']} = {cost} грн\n"
            else:
                cost = round(qty * props["price_per_m"])
                summary += f"{mat}: {qty:.1f} м × {props['price_per_m']} = {cost} грн\n"
            materials_cost += cost

    grand_total = total + materials_cost
    summary += f"\n💰 Робота: {total} грн"
    summary += f"\n🧾 Матеріали: {materials_cost} грн"
    summary += f"\n🔢 Загалом: {grand_total} грн"

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, summary)
    file_name = f"akt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(file_name)

    await query.message.reply_text("Ось ваш акт у PDF:")
    await query.message.reply_document(document=InputFile(file_name))

    history_file = "history.json"
    record = {
        "date": context.user_data["date"],
        "name": context.user_data["name"],
        "address": context.user_data["address"],
        "works": context.user_data["works"],
        "total": total,
        "materials_total": materials_cost,
        "grand_total": grand_total,
        "file": file_name,
    }
    try:
        if os.path.exists(history_file):
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = []
        history.append(record)
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Помилка збереження історії:", e)

    context.user_data.clear()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Скасовано.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END


handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_address)],
        ASK_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_date)],
        ASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_date)],
        COLLECT_WORK: [
            CallbackQueryHandler(finish_collection, pattern="^done$"),
            CallbackQueryHandler(collect_work),
        ],
        CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_work_amount)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)


async def ask_gpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("⛔️ Доступ заборонено.")
        return

    if not context.args:
        await update.message.reply_text(
            "Напишіть питання після команди. Приклад: /ask_gpt Як вибрати автомат?"
        )
        return

    prompt = " ".join(context.args)
    await update.message.reply_text("🤖 Думаю...")

    try:
        import requests

        headers = {
            "Authorization": f"Bearer {GPT_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
        }
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
        )
        result = response.json()
        reply = result["choices"][0]["message"]["content"]
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Помилка AI: {e}")


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history_file = "history.json"
    if not os.path.exists(history_file):
        await update.message.reply_text("Історія поки що порожня.")
        return

    with open(history_file, "r", encoding="utf-8") as f:
        history = json.load(f)

    if not history:
        await update.message.reply_text("Записів не знайдено.")
        return

    message = "📜 Історія актів:\n"
    for i, record in enumerate(history[-10:], 1):
        message += f"{i}. {record['date']} — {record['name']} — {record['total']} грн\n"

    buttons = [
        [InlineKeyboardButton(f"Отримати PDF #{i}", callback_data=f"get_{i-1}")]
        for i in range(1, min(11, len(history) + 1))
    ]

    await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(buttons))


async def send_pdf_from_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    index = int(query.data.split("_")[1])
    history_file = "history.json"
    with open(history_file, "r", encoding="utf-8") as f:
        history = json.load(f)
    record = history[-10:][index]
    file_path = record["file"]
    if os.path.exists(file_path):
        await query.message.reply_document(document=InputFile(file_path))
    else:
        await query.message.reply_text("PDF файл не знайдено. Можливо, його було видалено.")


async def main() -> None:
    if BOT_TOKEN is None:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("історія", show_history))
    application.add_handler(CommandHandler("ask_gpt", ask_gpt))
    application.add_handler(CallbackQueryHandler(send_pdf_from_history, pattern=r"^get_\d+$"))
    application.add_handler(handler)

    await application.run_polling()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
