import asyncio
import pytz
import threading
import http.server
import socketserver
import os
import time
import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import Conflict, TelegramError

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token and channel IDs
BOT_TOKEN = "7063656971:AAHMPxy3k0PMvf1Qi8badhPmZCgOEmRsE5k"
PUBLIC_CHANNEL_ID = -1002169622035
VIP_CHANNEL_ID = -1002291654577

# User state storage (using dictionary for fast access)
user_states = {}

# List of currency pairs
OTC_PAIRS = [
    "USDARS-OTC", "USDINR-OTC", "USDMXN-OTC", "USDTRY-OTC", 
    "USDBRL-OTC", "USDBDT-OTC", "USDPKR-OTC", "USDPHP-OTC", 
    "USDIDR-OTC", "USDCOP-OTC", "USDNGN-OTC", "USDEGP-OTC", 
    "USDDZD-OTC", "USDZAR-OTC", "EURUSD-OTC", "EURGBP-OTC",
    "NZDCHF-OTC", "NZDCAD-OTC", "NZDJPY-OTC", "NZDUSD-OTC", 
    "AUDNZD-OTC", "EURNZD-OTC", "CADCHF-OTC", "EURSGD-OTC"
]

LIVE_PAIRS = [
    "EURUSD (LIVE)", "EURJPY (LIVE)", "EURGBP (LIVE)", "EURCAD (LIVE)",
    "GBPUSD (LIVE)", "GBPJPY (LIVE)", "EURAUD (LIVE)", "CHFJPY (LIVE)",
    "CADJPY (LIVE)", "AUDUSD (LIVE)", "AUDCAD (LIVE)", "USDJPY (LIVE)"
]

# Helper function to create chunked keyboard - optimized for speed
def create_chunked_keyboard(items, prefix="", cols=3):
    keyboard = []
    for i in range(0, len(items), cols):
        row = [InlineKeyboardButton(item, callback_data=f"{prefix}:{item}") for item in items[i:i+cols]]
        keyboard.append(row)
    return keyboard

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_states[user_id] = {"step": "channel_selection"}
    
    keyboard = [
        [
            InlineKeyboardButton("Public Channel", callback_data="channel:public"),
            InlineKeyboardButton("VIP Channel", callback_data="channel:vip")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Welcome to Trading Signal Generator Bot!\n\nPlease select the channel where you want to send the signal:",
        reply_markup=reply_markup
    )

# Callback query handler - optimized for speed
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    # Use fast answer to avoid telegram wait_time
    await query.answer(cache_time=0)
    
    user_id = update.effective_user.id
    if user_id not in user_states:
        user_states[user_id] = {"step": "channel_selection"}
    
    callback_data = query.data
    
    # Handle channel selection
    if callback_data.startswith("channel:"):
        channel_type = callback_data.split(":")[1]
        user_states[user_id]["channel"] = channel_type
        user_states[user_id]["step"] = "market_selection"
        
        keyboard = [
            [
                InlineKeyboardButton("LIVE Market", callback_data="market:live"),
                InlineKeyboardButton("OTC Market", callback_data="market:otc")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Please select the market type:",
            reply_markup=reply_markup
        )
    
    # Handle market selection
    elif callback_data.startswith("market:"):
        market_type = callback_data.split(":")[1]
        user_states[user_id]["market"] = market_type
        user_states[user_id]["step"] = "currency_selection"
        
        if market_type == "otc":
            keyboard = create_chunked_keyboard(OTC_PAIRS, "currency", 2)
        else:  # live
            keyboard = create_chunked_keyboard(LIVE_PAIRS, "currency", 2)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Please select a currency pair:",
            reply_markup=reply_markup
        )
    
    # Handle currency selection
    elif callback_data.startswith("currency:"):
        currency_pair = callback_data.split(":")[1]
        user_states[user_id]["currency"] = currency_pair
        user_states[user_id]["step"] = "time_selection"
        
        # Generate the next 5 minutes in Sao Paulo time - optimized
        sao_paulo_tz = pytz.timezone('America/Sao_Paulo')
        now = datetime.now(sao_paulo_tz)
        
        # Get the current minute and then add 1 to start from next minute
        current_minute = now.replace(second=0, microsecond=0)
        next_minute = current_minute + timedelta(minutes=1)
        
        times = []
        time_values = []
        for i in range(5):
            time_option = next_minute + timedelta(minutes=i)
            formatted_time = time_option.strftime("%H:%M:00")
            times.append(formatted_time)
            time_values.append(formatted_time)
        
        # Use the full time strings for both display and callback data
        keyboard = []
        for i in range(0, len(times), 3):
            row = []
            for j in range(i, min(i+3, len(times))):
                row.append(InlineKeyboardButton(
                    times[j], 
                    callback_data=f"time:{time_values[j]}"
                ))
            keyboard.append(row)
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Please select the check-in time (Sao Paulo time):",
            reply_markup=reply_markup
        )
    
    # Handle time selection
    elif callback_data.startswith("time:"):
        # Store the full time value exactly as it appears in the button
        time_value = callback_data.split(":", 1)[1]  # Use 1 to get everything after the first colon
        user_states[user_id]["time"] = time_value
        user_states[user_id]["step"] = "direction_selection"
        
        keyboard = [
            [
                InlineKeyboardButton("🟢 UP", callback_data="direction:up"),
                InlineKeyboardButton("🔴 DOWN", callback_data="direction:down")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Please select the direction:",
            reply_markup=reply_markup
        )
    
    # Handle direction selection
    elif callback_data.startswith("direction:"):
        direction = callback_data.split(":")[1]
        user_states[user_id]["direction"] = "🟢 UP" if direction == "up" else "🔴 DOWN"
        user_states[user_id]["step"] = "preview"
        
        # Generate the signal preview
        signal = generate_signal(user_states[user_id])
        
        keyboard = [
            [InlineKeyboardButton("Send to Channel", callback_data="send:signal")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Preview of your signal:\n\n{signal}",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    
    # Handle send signal
    elif callback_data.startswith("send:"):
        signal = generate_signal(user_states[user_id])
        
        if user_states[user_id]["channel"] == "public":
            # Add the registration button for public channel
            keyboard = [
                [InlineKeyboardButton("📲 Quotex Registration", url="https://www.quotex.com/sign-up")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send to public channel
            await context.bot.send_message(
                chat_id=PUBLIC_CHANNEL_ID,
                text=signal,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            channel_name = "Public Channel"
        else:
            # Send to VIP channel
            await context.bot.send_message(
                chat_id=VIP_CHANNEL_ID,
                text=signal,
                parse_mode="HTML"
            )
            channel_name = "VIP Channel"
        
        await query.edit_message_text(
            f"Signal successfully sent to {channel_name}!"
        )
        
        # Reset user state
        user_states[user_id] = {"step": "channel_selection"}

# Generate signal text - with gap after direction and using full time format
def generate_signal(state):
    return (
        f"<b>📊 Currency: {state['currency']}</b>\n"
        f"<b>⏳ Expiration: M1</b>\n"
        f"<b>⏱️ Check-in: {state['time']}</b>\n"
        f"<b>↕️ Direction: {state['direction']}</b>\n"
        f"\n"  # Gap after direction
        f"<b>✅¹ 1-STEP MARTINGALE (FMG)</b>"
    )

# Error handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to the developer."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    if isinstance(context.error, Conflict):
        logger.warning("Bot conflict detected. Waiting before retrying...")
        # Sleep for a while to let the other instance release the connection
        await asyncio.sleep(30)
    elif isinstance(context.error, TelegramError):
        logger.error(f"Telegram error: {context.error}")

# Simple HTTP Server for Render health checks
class SimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'Bot is running!')
    
    def log_message(self, format, *args):
        # Suppress HTTP server logs to reduce noise
        pass

def run_web_server():
    try:
        # Get port from environment or default to 10000
        port = int(os.environ.get('PORT', 10000))
        handler = SimpleHTTPRequestHandler
        
        with socketserver.TCPServer(("", port), handler) as httpd:
            logger.info(f"Web server started at port {port}")
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"Web server error: {e}")

# Setup and run the bot with optimized settings
def main() -> None:
    try:
        # Start web server in a separate thread
        server_thread = threading.Thread(target=run_web_server, daemon=True)
        server_thread.start()
        
        # Create the Application with higher worker count for faster processing
        application = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        # Use webhook mode if on Render (based on environment)
        if 'RENDER' in os.environ:
            port = int(os.environ.get('PORT', 10000))
            webhook_url = os.environ.get('RENDER_EXTERNAL_URL')
            
            if webhook_url:
                logger.info(f"Starting bot in webhook mode at {webhook_url}")
                application.run_webhook(
                    listen="0.0.0.0",
                    port=port,
                    url_path=BOT_TOKEN,
                    webhook_url=f"{webhook_url}/{BOT_TOKEN}"
                )
            else:
                # Fall back to polling with safeguards if webhook URL not set
                logger.info("Starting bot in polling mode")
                application.run_polling(
                    drop_pending_updates=True,
                    allowed_updates=["callback_query", "message"],
                    close_loop=False
                )
        else:
            # Local development - use polling
            logger.info("Starting bot in polling mode (local)")
            application.run_polling(
                drop_pending_updates=True,
                allowed_updates=["callback_query", "message"],
                close_loop=False
            )
    except Exception as e:
        logger.error(f"Main thread error: {e}")

if __name__ == "__main__":
    main()