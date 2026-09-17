"""Telegram Bot Client integration for Nivaran AI.

Ported from Node.js prototype (`index.js` lines 48-135).
Uses python-telegram-bot async application runner in long polling mode.
"""

import re
import html
import logging
import asyncio
from typing import Optional
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from src.config import TELEGRAM_BOT_TOKEN
from src.services.chat_service import process_incoming_message, get_or_create_user, get_store_orders_by_email
from src.services.email_service import decode_email_token
from src.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

_telegram_app: Optional[Application] = None


def convert_markdown_to_telegram_html(text: str) -> str:
    """Converts standard LLM Markdown syntax into clean Telegram HTML entities.
    
    Transforms **word** -> <b>word</b> so words are highlighted in Telegram without showing raw ** asterisks.
    """
    if not text:
        return ""

    # Convert **bold** or __bold__ to <b>bold</b>
    formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    formatted = re.sub(r'__(.*?)__', r'<b>\1</b>', formatted, flags=re.DOTALL)

    # Convert `code` to <code>code</code>
    formatted = re.sub(r'`(.*?)`', r'<code>\1</code>', formatted)

    return formatted


async def safe_reply_markdown(update: Update, text: str) -> None:
    """Sends a Telegram message with HTML/Markdown entities enabled for highlighted bold words.

    Falls back to plain text if Telegram API fails to parse entities.
    """
    if not update.message or not text:
        return

    formatted_html = convert_markdown_to_telegram_html(text)

    try:
        # Primary: Send with HTML formatting enabled so <b>word</b> is highlighted in Telegram
        await update.message.reply_text(formatted_html, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"⚠️ Telegram HTML parsing fallback triggered ({e}), sending plain text response.")
        clean_text = text.replace("**", "").replace("__", "")
        await update.message.reply_text(clean_text)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for Telegram /start command with deep-link token & order tracking support."""
    if not update.message:
        return

    user = update.effective_user
    telegram_id = user.id if user else 0
    display_name = user.full_name if user else "User"

    # Ensure user record exists in Supabase users table
    db_user = get_or_create_user(telegram_id, display_name)
    user_email = db_user.get("email") if db_user else None

    # Check for deep-linking payload (e.g., /start em_a2FrYWt1bmc1N0BnbWFpbC5jb20 or /start ORD-12345)
    if context.args and len(context.args) > 0:
        payload = context.args[0].strip()

        # Case A: Encrypted / encoded email token link from order confirmation email
        decoded_email = decode_email_token(payload)
        if decoded_email:
            logger.info(f"🔗 Processing Telegram email token link for '{decoded_email}' by user {display_name} ({telegram_id})")
            
            # Save user with email in users table
            get_or_create_user(telegram_id, display_name, email=decoded_email)
            user_email = decoded_email

            # Fetch active store orders for this email
            user_orders = get_store_orders_by_email(decoded_email)
            if user_orders:
                order_summaries = []
                for o in user_orders:
                    items_str_list = []
                    for item in o.get("items", []):
                        p_name = (item.get("store_products") or {}).get("name", "Product")
                        qty = item.get("quantity", 1)
                        items_str_list.append(f"{p_name} (x{qty})")
                    items_summary = ", ".join(items_str_list) if items_str_list else "Purchased Items"
                    order_summaries.append(
                        f"📦 **Order #{o['id']}**\n"
                        f"• **Status:** `{o.get('status', 'processing').title()}`\n"
                        f"• **Total:** `${float(o.get('total', 0)):.2f}`\n"
                        f"• **Items:** {items_summary}"
                    )
                summary_text = "\n\n".join(order_summaries)
                verified_reply = (
                    f"👋 Hello {display_name}! Welcome to ShopNest Customer Support.\n\n"
                    f"✅ **Email Verified ({decoded_email})**\n"
                    f"Here are your active order details:\n\n"
                    f"{summary_text}\n\n"
                    "Which order or service would you like assistance with today?"
                )
            else:
                verified_reply = (
                    f"👋 Hello {display_name}! Welcome to ShopNest Support.\n\n"
                    f"Your email (`<b>{decoded_email}</b>`) has been verified, but no active orders were found under this account.\n\n"
                    "It looks like you're a new customer! What would you like to know about us? "
                    "Feel free to ask about our products, store policies, shipping options, or how to place an order!"
                )

            await safe_reply_markdown(update, verified_reply)
            return

        # Case B: Legacy order ID payload
        elif payload.startswith("ORD-"):
            order_id = payload
            logger.info(f"🔗 Processing Telegram deep link for order '{order_id}' by user {display_name} ({telegram_id})")

            product_name = "your purchased item"
            try:
                supabase = get_supabase_client()
                # Update user_id on orders table
                supabase.table("orders").update({"user_id": telegram_id}).eq("id", order_id).execute()

                # Get product details if available
                res = supabase.table("orders").select("product_id, products(name)").eq("id", order_id).execute()
                if res.data and len(res.data) > 0:
                    item_data = res.data[0]
                    p_info = item_data.get("products") or {}
                    product_name = p_info.get("name", product_name)
            except Exception as e:
                logger.error(f"❌ Error linking order '{order_id}' to user {telegram_id}: {e}")

            link_success_text = (
                f"🎉 **Order Linked Successfully!**\n\n"
                f"Hi {display_name}, your order **#{order_id}** ({product_name}) has been linked to your Telegram account!\n\n"
                f"📦 **Current Status:** `Processing`\n\n"
                f"You can ask me anytime about your order status, shipping updates, or return policies!"
            )
            await safe_reply_markdown(update, link_success_text)
            return

    if user_email:
        welcome_text = (
            f"👋 Hello {display_name}! Welcome back to ShopNest Support.\n\n"
            f"Your registered email is `<b>{user_email}</b>`.\n\n"
            "Ask me any question about your active orders, shipping, returns, or store policies!"
        )
    else:
        welcome_text = (
            f"👋 Hello {display_name}! Welcome to ShopNest Customer Support Assistant.\n\n"
            "Please reply with your registered **email address** so I can retrieve your order details and assist you!"
        )
    await safe_reply_markdown(update, welcome_text)




async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main message handler for incoming Telegram messages.

    Ported from `index.js` lines 57-131:
    - Extracts sender info and text.
    - Delegates processing to `process_incoming_message`.
    - Sends response reply to Telegram user with HTML highlighted bold words.
    """
    if not update.message or not update.message.text:
        return

    incoming_msg = update.message.text.strip()
    if incoming_msg.startswith('/'):
        return

    user = update.effective_user
    telegram_id = user.id if user else 0
    display_name = user.full_name if user else "User"

    logger.info(f"\n📩 Incoming Telegram message from {display_name} ({telegram_id}): '{incoming_msg}'")

    try:
        # Show typing status in Telegram chat
        if update.effective_chat:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        # Run chat service pipeline asynchronously in threadpool
        reply_text = await asyncio.to_thread(
            process_incoming_message,
            telegram_id,
            display_name,
            incoming_msg
        )

        if not reply_text or not reply_text.strip():
            reply_text = (
                "Hello! I'm here to help you with any questions about ShopNest orders, "
                "shipping options, return policies, or store hours. How can I assist you?"
            )

        logger.info(f"📤 Sending Telegram reply to {display_name} with highlighted bold words...")
        await safe_reply_markdown(update, reply_text)
        logger.info("✅ Telegram reply sent successfully.")
    except Exception as e:
        logger.error(f"❌ Error handling Telegram message: {e}", exc_info=True)
        await safe_reply_markdown(
            update,
            "I apologize, but I'm having trouble processing that request right now. "
            "Please try asking again, or let me know if you need help with returns, shipping, or order tracking."
        )


def setup_telegram_application() -> Optional[Application]:
    """Builds and configures the Telegram Bot application."""
    global _telegram_app

    if not TELEGRAM_BOT_TOKEN:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN is missing in environment variables!")
        logger.warning("👉 Add TELEGRAM_BOT_TOKEN=your_token_here to backend/.env")
        return None

    try:
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        _telegram_app = app
        logger.info("🚀 Telegram Bot Application configured successfully.")
        return app
    except Exception as e:
        logger.error(f"❌ Error initializing Telegram application: {e}")
        return None


async def start_telegram_polling() -> None:
    """Starts Telegram Bot polling background loop."""
    app = setup_telegram_application()
    if app:
        logger.info("🚀 Starting Telegram Bot polling loop...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
