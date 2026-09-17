import base64
import email.utils
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any

from src.config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SENDER_EMAIL,
    TELEGRAM_BOT_USERNAME,
)

logger = logging.getLogger(__name__)


def encode_email_token(email: str) -> str:
    """Encodes email address into a URL-safe token prefixed with 'em_'."""
    if not email:
        return ""
    b64 = base64.urlsafe_b64encode(email.strip().lower().encode("utf-8")).decode("utf-8").rstrip("=")
    return f"em_{b64}"


def decode_email_token(token: str) -> str:
    """Decodes email address from a URL-safe token prefixed with 'em_'."""
    if not token or not token.startswith("em_"):
        return ""
    try:
        raw_b64 = token[3:]
        padding = 4 - (len(raw_b64) % 4)
        if padding != 4:
            raw_b64 += "=" * padding
        email_bytes = base64.urlsafe_b64decode(raw_b64)
        email = email_bytes.decode("utf-8").strip().lower()
        if "@" in email and "." in email:
            return email
    except Exception as e:
        logger.warning(f"⚠️ Could not decode email token '{token}': {e}")
    return ""


def generate_order_confirmation_html(
    customer_name: str,
    order_id: str,
    total: float,
    items: List[Dict[str, Any]],
    customer_email: str = ""
) -> str:
    """Generates styled HTML email body for order confirmation."""
    bot_username = TELEGRAM_BOT_USERNAME.replace("@", "").strip() or "NivaranAiSupportBot"
    token = encode_email_token(customer_email) if customer_email else order_id
    bot_link = f"https://t.me/{bot_username}?start={token}"


    items_rows_html = ""
    for item in items:
        p_name = item.get("product_name", "Item")
        qty = item.get("quantity", 1)
        subtotal = item.get("subtotal", 0.0)
        items_rows_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">{p_name}</td>
            <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; text-align: center;">{qty}</td>
            <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; text-align: right;">${subtotal:.2f}</td>
        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f5f7; margin: 0; padding: 20px; }}
            .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
            .header {{ background: linear-gradient(135deg, #4f46e5, #7c3aed); color: #ffffff; padding: 24px; text-align: center; }}
            .body {{ padding: 24px; color: #374151; line-height: 1.6; }}
            .order-badge {{ display: inline-block; background: #e0e7ff; color: #4338ca; padding: 6px 12px; border-radius: 20px; font-weight: 700; margin: 12px 0; }}
            .table {{ width: 100%; border-collapse: collapse; margin-top: 16px; margin-bottom: 16px; }}
            .table th {{ background: #f9fafb; text-align: left; padding: 10px; border-bottom: 2px solid #e5e7eb; }}
            .total-row {{ font-weight: bold; font-size: 1.1em; color: #4f46e5; }}
            .support-box {{ background: #f5f3ff; border: 1px solid #c7d2fe; border-radius: 8px; padding: 16px; text-align: center; margin-top: 24px; }}
            .btn-telegram {{ display: inline-block; background: #0088cc; color: #ffffff; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 10px; }}
            .footer {{ background: #f9fafb; text-align: center; padding: 16px; font-size: 0.85em; color: #9ca3af; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <h1 style="margin:0; font-size: 24px;">🛍️ ShopNest Order Confirmed!</h1>
                <p style="margin:4px 0 0 0; opacity: 0.9;">Thank you for your order, {customer_name}!</p>
            </div>
            <div class="body">
                <p>Hello <strong>{customer_name}</strong>,</p>
                <p>We've received your order and are currently processing it. Here are your order details:</p>
                
                <div style="text-align: center;">
                    <span class="order-badge">Order ID: #{order_id}</span>
                </div>

                <table class="table">
                    <thead>
                        <tr>
                            <th>Item</th>
                            <th style="text-align: center;">Qty</th>
                            <th style="text-align: right;">Price</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_rows_html}
                        <tr>
                            <td colspan="2" style="padding: 12px 10px; text-align: right; font-weight: bold;">Total Amount Paid:</td>
                            <td style="padding: 12px 10px; text-align: right;" class="total-row">${total:.2f}</td>
                        </tr>
                    </tbody>
                </table>

                <div class="support-box">
                    <h4 style="margin:0 0 8px 0; color: #3730a3;">💬 Need Help or Order Tracking?</h4>
                    <p style="margin:0 0 12px 0; font-size: 0.9em; color: #4b5563;">
                        Connect with our 24/7 AI Customer Support Bot on Telegram! Simply start the chat and enter your email address to track live status or ask questions.
                    </p>
                    <a href="{bot_link}" class="btn-telegram" target="_blank">Launch Customer Support Bot</a>
                </div>
            </div>
            <div class="footer">
                &copy; ShopNest Powered by Nivaran AI. All rights reserved.
            </div>
        </div>
    </body>
    </html>
    """
    return html_content


def generate_order_confirmation_text(
    customer_name: str,
    order_id: str,
    total: float,
    items: List[Dict[str, Any]],
    customer_email: str = ""
) -> str:
    """Generates plain text email body fallback."""
    bot_username = TELEGRAM_BOT_USERNAME.replace("@", "").strip() or "NivaranAiSupportBot"
    token = encode_email_token(customer_email) if customer_email else order_id
    bot_link = f"https://t.me/{bot_username}?start={token}"

    items_text = "\n".join(
        [f"- {item.get('product_name', 'Item')} (x{item.get('quantity', 1)}): ${item.get('subtotal', 0.0):.2f}" for item in items]
    )

    return f"""Hello {customer_name},

Thank you for your order with ShopNest!

Order ID: #{order_id}
Total Amount: ${total:.2f}

Items Purchased:
{items_text}

Need Help or Order Tracking?
Connect with our AI Customer Support Bot on Telegram:
{bot_link}

Thank you for shopping with us!
ShopNest Team
"""


def send_order_confirmation_email(
    customer_name: str,
    customer_email: str,
    order_id: str,
    total: float,
    items: List[Dict[str, Any]]
) -> bool:
    """Sends confirmation email to customer.
    
    If SMTP parameters are configured, sends real SMTP email.
    Otherwise, logs formatted confirmation email body.
    """
    html_body = generate_order_confirmation_html(customer_name, order_id, total, items, customer_email=customer_email)
    text_body = generate_order_confirmation_text(customer_name, order_id, total, items, customer_email=customer_email)

    is_smtp_configured = (
        SMTP_USER and 
        SMTP_PASSWORD and 
        "your_email" not in SMTP_USER and 
        "your_app_password" not in SMTP_PASSWORD
    )

    if is_smtp_configured:
        try:
            msg = MIMEMultipart("alternative")
            sender = SENDER_EMAIL or SMTP_USER
            msg["Subject"] = f"ShopNest Order Confirmation #{order_id}"
            msg["From"] = sender
            msg["To"] = customer_email
            msg["Reply-To"] = sender
            msg["Date"] = email.utils.formatdate(localtime=True)
            msg["Message-ID"] = email.utils.make_msgid(domain="shopnest.com")

            # Attach plain text and HTML versions for spam score reduction
            part_text = MIMEText(text_body, "plain", "utf-8")
            part_html = MIMEText(html_body, "html", "utf-8")
            msg.attach(part_text)
            msg.attach(part_html)

            logger.info(f"📧 Attempting to send confirmation email for Order #{order_id} via SMTP to {customer_email}...")

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(sender, [customer_email], msg.as_string())

            logger.info(f"✅ Confirmation email sent successfully to {customer_email} via SMTP!")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send SMTP confirmation email to {customer_email}: {e}")
            logger.info("ℹ️ Falling back to local confirmation email logging.")

    # Fallback log output when SMTP is unconfigured or fails
    bot_username = TELEGRAM_BOT_USERNAME.replace("@", "").strip() or "NivaranAiSupportBot"
    token = encode_email_token(customer_email) if customer_email else order_id
    logger.info("=" * 60)
    logger.info(f"📧 [CONFIRMATION EMAIL SIMULATION] To: {customer_email}")
    logger.info(f"Subject: ShopNest Order Confirmation #{order_id}")
    logger.info(f"Customer: {customer_name} | Total: ${total:.2f}")
    logger.info(f"Telegram Bot Link: https://t.me/{bot_username}?start={token}")
    logger.info("=" * 60)
    return True


