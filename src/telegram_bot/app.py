from src.telegram_bot.handlers import create_bot_app


def run_telegram_bot(binance_client=None, rl_agent=None, tuner=None, weighter=None, guard=None, strategy_manager=None):
    app = create_bot_app(binance_client)
    if rl_agent:
        app.bot_data["rl_agent"] = rl_agent
    if tuner:
        app.bot_data["tuner"] = tuner
    if weighter:
        app.bot_data["weighter"] = weighter
    if guard:
        app.bot_data["guard"] = guard
    if strategy_manager:
        app.bot_data["strategy_manager"] = strategy_manager
    app.run_polling()
