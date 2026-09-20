"""FastAPI Application Entrypoint for Nivaran AI Backend.

Wires REST Admin endpoints, database connection initialization,
and Telegram Bot polling background service lifecycle.
"""

import os
import sys
import logging
import asyncio
from contextlib import asynccontextmanager

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import random
import string
from datetime import datetime
from pydantic import BaseModel, Field
from fastapi import FastAPI, Request, Response, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from telegram import Update
from src.config import PORT, HOST, TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME, TELEGRAM_MODE, WEBHOOK_URL
from src.api.admin_routes import router as admin_router
from src.store.routes import store_router as store_router
from src.api.voice_routes import router as voice_router
from src.integrations.telegram_client import setup_telegram_application
from src.db.supabase_client import get_supabase_client

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

telegram_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan Context Manager for background services initialization."""
    logger.info("⚡ Nivaran AI Backend initializing...")
    global telegram_app

    if TELEGRAM_BOT_TOKEN:
        try:
            telegram_app = setup_telegram_application()
            if telegram_app:
                await telegram_app.initialize()
                await telegram_app.start()

                if TELEGRAM_MODE == "polling":
                    await telegram_app.updater.start_polling()
                    logger.info("🚀 Telegram Bot running in polling mode.")
                elif TELEGRAM_MODE == "webhook" and WEBHOOK_URL:
                    webhook_endpoint = f"{WEBHOOK_URL.rstrip('/')}/api/telegram/webhook"
                    await telegram_app.bot.set_webhook(url=webhook_endpoint)
                    logger.info(f"🚀 Telegram Bot running in webhook mode at {webhook_endpoint}")
        except Exception as e:
            logger.error(f"❌ Failed to start Telegram Bot: {e}")
    else:
        logger.warning("⚠️ Running in REST API mode only (TELEGRAM_BOT_TOKEN not provided).")

    yield  # Server runs here

    # Shutdown hooks
    logger.info("🛑 Nivaran AI Backend shutting down...")
    if telegram_app:
        if telegram_app.updater and telegram_app.updater.running:
            await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("👋 Telegram Bot stopped.")


app = FastAPI(
    title="Nivaran AI Backend API",
    description="Python FastAPI backend powering RAG Customer Support and Admin Panel integrations.",
    version="1.0.0",
    lifespan=lifespan
)

from fastapi.staticfiles import StaticFiles

# Enable CORS for Frontend Admin Panel development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust allowed origins for production deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Admin, Store & Voice REST API Routes
app.include_router(admin_router)
app.include_router(store_router)
app.include_router(voice_router)

# Mount Static Frontends (Admin Panel & E-Commerce Storefront)
frontend_dir = os.path.abspath(os.path.join(backend_dir, "..", "frontend"))
if os.path.exists(os.path.join(frontend_dir, "admin")):
    app.mount("/admin", StaticFiles(directory=os.path.join(frontend_dir, "admin"), html=True), name="admin")

store_dir = os.path.join(frontend_dir, "src", "store") if os.path.exists(os.path.join(frontend_dir, "src", "store")) else os.path.join(frontend_dir, "store")
if os.path.exists(store_dir):
    app.mount("/store", StaticFiles(directory=store_dir, html=True), name="store")




@app.get("/", tags=["Health Check"])
async def root():
    """Root status endpoint."""
    return {
        "service": "Nivaran AI Backend",
        "status": "online",
        "version": "1.0.0",
        "docs_url": "/docs"
    }


@app.get("/health", tags=["Health Check"])
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


@app.get("/api/products", tags=["Storefront Products"])
async def list_products():
    """Retrieves all available products from the Supabase database with fallback."""
    try:
        supabase = get_supabase_client()
        res = supabase.table("products").select("*").order("id").execute()
        if res.data and len(res.data) > 0:
            return res.data
    except Exception as e:
        logger.warning(f"⚠️ Could not fetch products from Supabase database: {e}")

    # Fallback products matching migration 04 schema
    return [
        {
            "id": 1,
            "name": "Wireless Headphones",
            "price": 99.99,
            "description": "Premium noise-canceling wireless headphones with high-fidelity sound."
        },
        {
            "id": 2,
            "name": "Smartwatch",
            "price": 149.99,
            "description": "Next-gen fitness tracker and smartwatch with heart rate monitoring."
        },
        {
            "id": 3,
            "name": "Bluetooth Speaker",
            "price": 59.99,
            "description": "Portable waterproof Bluetooth speaker with deep bass."
        }
    ]


class CheckoutRequest(BaseModel):
    product_id: int = Field(..., description="ID of product being purchased")
    customer_name: str = Field(..., description="Name of customer purchasing item")


@app.post("/api/checkout", tags=["Storefront Checkout"])
async def checkout(payload: CheckoutRequest):
    """Processes product checkout, inserts order into database, and generates Telegram deep link."""
    random_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    order_id = f"ORD-{random_suffix}"
    now_iso = datetime.utcnow().isoformat()

    try:
        supabase = get_supabase_client()
        order_data = {
            "id": order_id,
            "product_id": payload.product_id,
            "user_id": None,
            "status": "processing",
            "created_at": now_iso
        }
        supabase.table("orders").insert(order_data).execute()
        logger.info(f"🛒 Order '{order_id}' created for product ID {payload.product_id} (Customer: '{payload.customer_name}')")
    except Exception as e:
        logger.error(f"❌ Failed to insert order '{order_id}' into Supabase: {e}")

    # Resolve bot username from running Telegram bot client or config setting
    bot_name = TELEGRAM_BOT_USERNAME
    if telegram_app and hasattr(telegram_app, "bot") and telegram_app.bot and telegram_app.bot.username:
        bot_name = telegram_app.bot.username

    if not bot_name:
        bot_name = "NivaranAiBot"

    telegram_deep_link = f"https://t.me/{bot_name}?start={order_id}"

    return {
        "status": "success",
        "order_id": order_id,
        "customer_name": payload.customer_name,
        "product_id": payload.product_id,
        "telegram_deep_link": telegram_deep_link
    }


@app.post("/api/telegram/webhook", tags=["Telegram Webhook"])
async def telegram_webhook(request: Request):
    """Processes incoming Telegram updates in webhook mode."""
    if not telegram_app:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error handling webhook update: {e}")
        return Response(status_code=status.HTTP_400_BAD_REQUEST)


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on http://{HOST}:{PORT}")
    uvicorn.run("src.main:app", host=HOST, port=PORT, reload=True)
