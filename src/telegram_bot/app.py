from src.telegram_bot.handlers import create_bot_app


def run_telegram_bot():
    app = create_bot_app()
    app.run_polling()
