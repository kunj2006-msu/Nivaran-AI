"""Chat Service Orchestrator for Nivaran AI.

Coordinates user resolution, conversational memory window retrieval, RAG retrieval,
LLM completion, message logging, and in-house escalation ticketing.
"""

import logging
from datetime import datetime
from typing import Tuple, List, Dict, Any
from src.config import CHAT_HISTORY_WINDOW, SIMILARITY_THRESHOLD
from src.db.supabase_client import get_supabase_client
from src.rag.retriever import retrieve_context, get_user_active_orders
from src.rag.generator import generate_llm_response
from src.services.escalation_service import evaluate_escalation_triggers, create_in_house_ticket

logger = logging.getLogger(__name__)


def get_or_create_user(telegram_id: int, name: str, email: str = None) -> Dict[str, Any]:
    """Ensures user exists in the `users` table and updates `last_active_at` and `email` if provided.

    Args:
        telegram_id: Telegram user ID.
        name: Display name or handle.
        email: Optional email address.

    Returns:
        User record dictionary.
    """
    now_iso = datetime.utcnow().isoformat()

    try:
        supabase = get_supabase_client()
        # Check existing user
        response = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
        if response.data and len(response.data) > 0:
            user = response.data[0]
            update_fields = {"last_active_at": now_iso, "name": name}
            if email:
                update_fields["email"] = email.strip().lower()
            supabase.table("users").update(update_fields).eq("id", user["id"]).execute()
            user.update(update_fields)
            return user

        # Create new user
        new_user_data = {
            "telegram_id": telegram_id,
            "name": name,
            "created_at": now_iso,
            "last_active_at": now_iso
        }
        if email:
            new_user_data["email"] = email.strip().lower()
        create_res = supabase.table("users").insert(new_user_data).execute()
        if create_res.data and len(create_res.data) > 0:
            return create_res.data[0]
        return {"id": 0, "telegram_id": telegram_id, "name": name, "email": email}
    except Exception as e:
        logger.error(f"Error upserting user telegram_id={telegram_id}: {e}")
        return {"id": 0, "telegram_id": telegram_id, "name": name, "email": email}


def update_user_email(telegram_id: int, email: str) -> None:
    """Updates the user's email in the users table."""
    if not telegram_id or not email:
        return
    try:
        supabase = get_supabase_client()
        supabase.table("users").update({
            "email": email.strip().lower(),
            "last_active_at": datetime.utcnow().isoformat()
        }).eq("telegram_id", telegram_id).execute()
        logger.info(f"📧 Updated user telegram_id={telegram_id} with email='{email}'")
    except Exception as e:
        logger.error(f"❌ Failed to update email for telegram_id={telegram_id}: {e}")


def get_store_orders_by_email(email: str) -> List[Dict[str, Any]]:
    """Fetches active store orders and items for a given email address."""
    if not email:
        return []
    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("store_orders")
            .select("*")
            .eq("email", email.strip().lower())
            .order("created_at", desc=True)
            .execute()
        )
        orders = res.data or []
        for o in orders:
            items_res = (
                supabase.table("store_order_items")
                .select("quantity, unit_price, store_products(name)")
                .eq("order_id", o["id"])
                .execute()
            )
            o["items"] = items_res.data or []
        return orders
    except Exception as e:
        logger.error(f"❌ Error fetching store_orders for email '{email}': {e}")
        return []



def fetch_recent_history(user_id: int, limit: int = CHAT_HISTORY_WINDOW) -> List[Dict[str, Any]]:
    """Pulls the last N messages for a user to construct short-term context.

    Uses `CHAT_HISTORY_WINDOW` (default 5).
    """
    if user_id <= 0:
        return []

    try:
        supabase = get_supabase_client()
        response = (
            supabase.table("chat_history")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        # Reverse to return in chronological order (oldest to newest)
        history = response.data or []
        return list(reversed(history))
    except Exception as e:
        logger.error(f"Error fetching chat history for user_id={user_id}: {e}")
        return []


def log_chat_message(user_id: int, role: str, content: str) -> None:
    """Logs a single message ('user' or 'assistant') to the `chat_history` table."""
    if user_id <= 0:
        return

    try:
        supabase = get_supabase_client()
        supabase.table("chat_history").insert({
            "user_id": user_id,
            "role": role,
            "content": content,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"Error logging chat message role={role} user_id={user_id}: {e}")


def format_history_for_prompt(history: List[Dict[str, Any]]) -> str:
    """Formats a list of history records into a prompt string."""
    formatted_lines = []
    for msg in history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        formatted_lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(formatted_lines)


def count_unresolved_turns(history: List[Dict[str, Any]]) -> int:
    """Calculates consecutive unresolved or low-confidence turns from recent history."""
    unresolved_indicators = [
        "escalat", "human support", "apologize", "unable to find",
        "don't have information", "not enough information", "representative", "ticket #"
    ]
    count = 0
    # Traverse from most recent messages backwards
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "").lower()
            if any(ind in content for ind in unresolved_indicators):
                count += 1
            else:
                break
    return count


def validate_order_ownership(telegram_id: int, order_id: str) -> bool:
    """Checks if an order_id exists in Supabase orders table and is linked to user's telegram_id.

    Args:
        telegram_id: Telegram user ID.
        order_id: Order string ID (e.g. 'ORD-EEZPW').

    Returns:
        True if valid and owned by user, False otherwise.
    """
    if not order_id or not telegram_id or telegram_id <= 0:
        return False
    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("orders")
            .select("id")
            .eq("id", order_id.upper().strip())
            .eq("user_id", telegram_id)
            .execute()
        )
        return bool(res.data and len(res.data) > 0)
    except Exception as e:
        logger.error(f"❌ Error validating order ownership for order '{order_id}' user {telegram_id}: {e}")
        return False


def process_incoming_message(telegram_id: int, user_display_name: str, message_text: str) -> str:
    """End-to-end orchestration pipeline for an incoming user message."""
    logger.info(f"📩 Processing message from user '{user_display_name}' ({telegram_id}): '{message_text[:50]}...'")

    try:
        # Step 1: User resolution
        user = get_or_create_user(telegram_id, user_display_name)
        user_id = user.get("id", 0)

        # Step 2: Fetch short-term history window (last CHAT_HISTORY_WINDOW messages)
        history_records = fetch_recent_history(user_id, limit=CHAT_HISTORY_WINDOW)
        formatted_history = format_history_for_prompt(history_records)
        recent_unresolved = count_unresolved_turns(history_records)

        # Log incoming user message
        log_chat_message(user_id, "user", message_text)

        # Step 1.5: Check if user provided an email address
        import re
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", message_text)
        if email_match:
            user_email = email_match.group(0).strip().lower()
            logger.info(f"📧 Extracted email '{user_email}' from telegram_id={telegram_id}")

            # Save email in users table
            update_user_email(telegram_id, user_email)

            # Retrieve active orders for this email
            active_orders = get_store_orders_by_email(user_email)

            if active_orders:
                order_summaries = []
                for o in active_orders:
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
                reply = (
                    f"✅ **Email Verified!** Here are your active order details:\n\n"
                    f"{summary_text}\n\n"
                    "Which order or service would you like assistance with today?"
                )
            else:
                reply = (
                    f"👋 Welcome to ShopNest! We couldn't find any existing orders associated with **{user_email}**.\n\n"
                    "It looks like you're a new customer! What would you like to know about us? "
                    "Feel free to ask about our products, store policies, shipping options, or how to place an order!"
                )

            log_chat_message(user_id, "assistant", reply)
            return reply


        # Check if the previous assistant turn was a ticket confirmation request or update prompt
        last_assistant_msg = ""
        prev_user_msg = ""
        for msg in reversed(history_records):
            if msg.get("role") == "assistant" and not last_assistant_msg:
                last_assistant_msg = msg.get("content", "")
            elif msg.get("role") == "user" and not prev_user_msg:
                prev_user_msg = msg.get("content", "")

        is_pending_ticket_prompt = (
            "reply yes to confirm" in last_assistant_msg.lower() or 
            "reply **yes** to confirm" in last_assistant_msg.lower() or
            "open an official support ticket" in last_assistant_msg.lower()
        )
        is_manual_format_prompt = (
            "order number: ord-" in last_assistant_msg.lower() or
            "reply in the following format" in last_assistant_msg.lower()
        )

        user_clean_text = "".join(c for c in message_text.lower() if c.isalnum() or c.isspace()).strip()

        # CASE 1: Handle user response to pending ticket confirmation request (Message 1)
        if is_pending_ticket_prompt:
            affirmative_words = {"yes", "yep", "yeah", "confirm", "sure", "ok", "yes please", "please do", "do it", "y", "correct"}
            update_words = {"update", "edit", "change", "correct", "wrong order", "modify"}
            cancel_words = {"cancel", "no ticket", "dont create", "don't create", "stop", "nevermind", "nvm"}

            # Sub-case A: User confirmed with YES -> Create Ticket with actual trigger reason & issue text!
            if any(w in user_clean_text.split() for w in affirmative_words) or user_clean_text in affirmative_words:
                user_orders = get_user_active_orders(telegram_id)
                linked_order_id = user_orders[0].get("id") if (user_orders and len(user_orders) > 0) else None

                import re
                match = re.search(r"ORD-[A-Za-z0-9]+", prev_user_msg + " " + last_assistant_msg, re.IGNORECASE)
                if match:
                    linked_order_id = match.group(0).upper()

                issue_desc = prev_user_msg if prev_user_msg else message_text

                # Dynamically evaluate exact trigger reason from customer's original query
                _, actual_reason = evaluate_escalation_triggers(
                    user_message=issue_desc,
                    max_similarity=0.0,
                    context_documents=[],
                    recent_unresolved_count=0
                )
                if not actual_reason:
                    actual_reason = "Customer reported damaged/defective product requiring escalation."

                created_ticket = create_in_house_ticket(
                    user_id=user_id,
                    escalation_reason=actual_reason,
                    order_id=linked_order_id,
                    issue_description=issue_desc,
                    issue=issue_desc
                )

                ticket_id = created_ticket.get("id") if created_ticket else "1"
                order_display = f"#{linked_order_id}" if linked_order_id else "Not linked"

                ticket_summary_reply = (
                    "🎉 **Support Ticket Created Successfully!**\n\n"
                    "📋 **Ticket Summary:**\n"
                    f"• **Ticket ID:** #{ticket_id}\n"
                    f"• **Order Number:** {order_display}\n"
                    f"• **Issue:** {issue_desc}\n"
                    "• **Status:** Open\n\n"
                    "Our customer support team has received your ticket and will review your issue shortly. Thank you for your patience!"
                )
                log_chat_message(user_id, "assistant", ticket_summary_reply)
                return ticket_summary_reply

            # Sub-case B: User replies UPDATE -> Send Format Prompt
            elif any(w in user_clean_text.split() for w in update_words) or user_clean_text in update_words:
                update_prompt_reply = (
                    "No problem! If you would like to update your details or specify a different order number, please reply in the following format:\n\n"
                    "Order Number: ORD-XXXXX\n"
                    "Issue: Your updated issue description here"
                )
                log_chat_message(user_id, "assistant", update_prompt_reply)
                return update_prompt_reply

            # Sub-case C: User replies CANCEL / NO TICKET / NO
            elif any(w in user_clean_text.split() for w in cancel_words) or user_clean_text in {"no", "cancel", "n"}:
                cancel_reply = "Understood! I have cancelled the support ticket creation request. Please let me know if there is anything else I can help you with!"
                log_chat_message(user_id, "assistant", cancel_reply)
                return cancel_reply

        # CASE 2: Handle custom format input (Order Number: ORD-XXXXX \n Issue: ...)
        import re
        is_formatted_submission = "order number:" in message_text.lower() or (is_manual_format_prompt and re.search(r"ORD-[A-Za-z0-9]+", message_text, re.IGNORECASE))

        if is_formatted_submission:
            order_match = re.search(r"ORD-[A-Za-z0-9]+", message_text, re.IGNORECASE)
            parsed_order_id = order_match.group(0).upper() if order_match else None

            issue_match = re.search(r"issue\s*:\s*(.*)", message_text, re.IGNORECASE | re.DOTALL)
            if issue_match and issue_match.group(1).strip():
                parsed_issue = issue_match.group(1).strip()
            else:
                # Cleanly strip out Order Number tag & Order ID pattern from message_text if no explicit "Issue:" prefix
                cleaned = message_text
                if parsed_order_id:
                    cleaned = re.sub(r"(?:Order\s*Number\s*:?\s*)?#?" + re.escape(parsed_order_id) + r"\s*[-:\n]*", "", cleaned, flags=re.IGNORECASE).strip()
                    cleaned = re.sub(r"^(?:Order\s*Number|Order)\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
                
                if cleaned:
                    parsed_issue = cleaned
                else:
                    # User only provided order number; find original issue description from history
                    original_issue = ""
                    for msg in reversed(history_records):
                        if msg.get("role") == "user":
                            c = msg.get("content", "").strip()
                            if c.lower() not in {"yes", "update", "cancel", "no", "y", "n"} and not re.fullmatch(r"(?:order\s*number\s*:?\s*)?#?ORD-[A-Za-z0-9]+", c, re.IGNORECASE):
                                original_issue = c
                                break
                    parsed_issue = original_issue if original_issue else message_text

            if parsed_order_id:
                # Validate order ownership in Supabase DB!
                is_valid = validate_order_ownership(telegram_id, parsed_order_id)
                if not is_valid:
                    invalid_order_reply = (
                        f"❌ **Invalid Order Number!** The order number `#{parsed_order_id}` was not found under your account.\n\n"
                        "Please enter a valid order number associated with your account in the format:\n"
                        "Order Number: ORD-XXXXX\n"
                        "Issue: Your issue description"
                    )
                    log_chat_message(user_id, "assistant", invalid_order_reply)
                    return invalid_order_reply

                # Dynamically evaluate trigger reason for submitted issue
                _, actual_reason = evaluate_escalation_triggers(
                    user_message=parsed_issue,
                    max_similarity=0.0,
                    context_documents=[],
                    recent_unresolved_count=0
                )
                if not actual_reason:
                    actual_reason = "Customer submitted updated order & issue details."

                # Valid Order! Create ticket in Supabase
                created_ticket = create_in_house_ticket(
                    user_id=user_id,
                    escalation_reason=actual_reason,
                    order_id=parsed_order_id,
                    issue_description=parsed_issue,
                    issue=parsed_issue
                )

                ticket_id = created_ticket.get("id") if created_ticket else "1"
                ticket_summary_reply = (
                    "🎉 **Support Ticket Created Successfully!**\n\n"
                    "📋 **Ticket Summary:**\n"
                    f"• **Ticket ID:** #{ticket_id}\n"
                    f"• **Order Number:** #{parsed_order_id}\n"
                    f"• **Issue:** {parsed_issue}\n"
                    "• **Status:** Open\n\n"
                    "Our customer support team has received your ticket and will review your issue shortly. Thank you for your patience!"
                )
                log_chat_message(user_id, "assistant", ticket_summary_reply)
                return ticket_summary_reply

        # Step 3: RAG Retrieval
        docs, max_similarity = retrieve_context(message_text, match_threshold=SIMILARITY_THRESHOLD, match_count=3)

        # Step 3.5: Fetch Active Customer Orders for Context Injection
        user_orders = get_user_active_orders(telegram_id)
        if user_orders:
            formatted_orders_list = []
            for o in user_orders:
                p_info = o.get("products") or {}
                p_name = p_info.get("name", "Product")
                p_price = p_info.get("price", "")
                price_str = f" (${p_price})" if p_price else ""
                formatted_orders_list.append(f"- Order #{o.get('id')}: {p_name}{price_str} | Status: {o.get('status')}")
            active_orders_formatted = "\n".join(formatted_orders_list)
        else:
            active_orders_formatted = "No linked active orders found for this customer account."

        # Step 5: Escalation Evaluation
        should_escalate, escalation_reason = evaluate_escalation_triggers(
            user_message=message_text,
            max_similarity=max_similarity,
            context_documents=docs,
            recent_unresolved_count=recent_unresolved
        )

        # STEP B: If query requires escalation -> Send Message 1 (Confirmation Request with 3 choices)
        if should_escalate:
            linked_order_id = user_orders[0].get("id") if (user_orders and len(user_orders) > 0) else None
            import re
            match = re.search(r"ORD-[A-Za-z0-9]+", message_text, re.IGNORECASE)
            if match:
                linked_order_id = match.group(0).upper()

            order_display = f"#{linked_order_id}" if linked_order_id else "Not specified"

            confirm_request_reply = (
                "I am very sorry to hear about the issue with your item.\n\n"
                "Before I submit your request to our customer support team, please confirm if you would like me to open an official support ticket:\n\n"
                "📋 **Proposed Ticket Details:**\n"
                f"• **Order Number:** {order_display}\n"
                f"• **Issue:** {message_text}\n"
                "• **Status:** Pending Confirmation\n\n"
                "**Options:**\n"
                "• Reply **YES** to confirm ticket creation as listed.\n"
                "• Reply **UPDATE** to correct or change the Order Number or Issue.\n"
                "• Reply **CANCEL** if you do not want to open a support ticket."
            )
            log_chat_message(user_id, "assistant", confirm_request_reply)
            return confirm_request_reply

        # Step 4: Normal LLM Reply Generation (Non-escalated queries)
        ai_reply = generate_llm_response(message_text, docs, formatted_history, active_orders_formatted)
        log_chat_message(user_id, "assistant", ai_reply)
        return ai_reply
    except Exception as e:
        logger.error(f"❌ Unhandled error in process_incoming_message: {e}", exc_info=True)
        return (
            "Hello! I am Nivaran AI, your ShopNest customer support assistant.\n\n"
            "I can help you with store questions, order tracking, shipping options, and returns. "
            "How may I assist you today?"
        )
