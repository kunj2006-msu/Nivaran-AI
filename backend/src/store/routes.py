"""FastAPI REST API routes for Customer Storefront (/api/store/...)."""

import logging
import random
import string
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, Path, status, BackgroundTasks

from src.db.supabase_client import get_supabase_client
from src.services.email_service import send_order_confirmation_email
from src.store.models import (

    StoreProduct,
    CreateOrderRequest,
    OrderResponse,
    OrderItemResponse,
)

logger = logging.getLogger(__name__)

store_router = APIRouter(
    prefix="/api/store",
    tags=["Storefront"]
)

# In-memory fallback product catalog with stock inventory
FALLBACK_STORE_PRODUCTS: List[dict] = [
    {
        "id": 1,
        "name": "Aura Wireless Headphones",
        "description": "Active noise cancelling wireless headphones with 40h battery life and spatial audio.",
        "price": 129.99,
        "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&auto=format&fit=crop&q=60",
        "stock": 15,
        "status": "active"
    },
    {
        "id": 2,
        "name": "Pulse Fitness Smartwatch",
        "description": "Waterproof fitness smartwatch with AMOLED display, heart rate tracking, and GPS.",
        "price": 179.99,
        "image_url": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&auto=format&fit=crop&q=60",
        "stock": 8,
        "status": "active"
    },
    {
        "id": 3,
        "name": "SonicBoom Bluetooth Speaker",
        "description": "Compact waterproof Bluetooth speaker delivering 360-degree immersive bass sound.",
        "price": 69.99,
        "image_url": "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=500&auto=format&fit=crop&q=60",
        "stock": 20,
        "status": "active"
    },
    {
        "id": 4,
        "name": "ZenErgo Mechanical Keyboard",
        "description": "RGB tactile wireless mechanical keyboard with hot-swappable switches and wrist rest.",
        "price": 119.99,
        "image_url": "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=500&auto=format&fit=crop&q=60",
        "stock": 5,
        "status": "active"
    },
    {
        "id": 5,
        "name": "Clarion HD Ergonomic Earbuds",
        "description": "True wireless in-ear earbuds with dual mic noise suppression and instant pairing.",
        "price": 49.99,
        "image_url": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=500&auto=format&fit=crop&q=60",
        "stock": 0,
        "status": "active"
    }
]


@store_router.get("/products", response_model=List[StoreProduct], summary="List storefront products")
async def list_store_products():
    """Retrieves all active customer-facing products with stock levels."""
    try:
        supabase = get_supabase_client()
        res = supabase.table("store_products").select("*").eq("status", "active").order("id").execute()
        if res.data and len(res.data) > 0:
            return res.data
    except Exception as e:
        logger.warning(f"⚠️ Could not fetch products from store_products table, using fallback data: {e}")

    return FALLBACK_STORE_PRODUCTS


@store_router.get("/products/{id}", response_model=StoreProduct, summary="Get product details")
async def get_store_product(id: int = Path(..., description="ID of product to retrieve")):
    """Retrieves single product detail by ID."""
    try:
        supabase = get_supabase_client()
        res = supabase.table("store_products").select("*").eq("id", id).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception as e:
        logger.warning(f"⚠️ DB lookup failed for product #{id}, checking fallback: {e}")

    # Check fallback list
    found = next((p for p in FALLBACK_STORE_PRODUCTS if p["id"] == id), None)
    if found:
        return found

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Product #{id} not found"
    )


@store_router.post("/orders", response_model=OrderResponse, summary="Submit customer store order")
async def create_store_order(payload: CreateOrderRequest):
    """Processes order submission: validates stock, calculates total server-side, and records order."""
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must contain at least one item."
        )

    # Simple email & phone client format check validation
    if "@" not in payload.customer.email or "." not in payload.customer.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid customer email format."
        )

    db_products_map = {}
    use_db = True

    try:
        supabase = get_supabase_client()
        res = supabase.table("store_products").select("*").execute()
        if res.data:
            for item in res.data:
                db_products_map[item["id"]] = item
        else:
            use_db = False
    except Exception as e:
        logger.warning(f"⚠️ Supabase error fetching store_products, fallback to memory: {e}")
        use_db = False

    if not use_db or not db_products_map:
        for p in FALLBACK_STORE_PRODUCTS:
            db_products_map[p["id"]] = p

    # 1. Stock & Price Validation
    order_items_response: List[OrderItemResponse] = []
    total_amount = 0.0

    for item_req in payload.items:
        p_id = item_req.product_id
        qty = item_req.quantity

        if p_id not in db_products_map:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product ID #{p_id} does not exist in store catalog."
            )

        product = db_products_map[p_id]
        current_stock = int(product.get("stock", 0))

        if qty > current_stock:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for '{product['name']}'. Requested: {qty}, Available stock: {current_stock}."
            )

        unit_price = float(product["price"])
        item_subtotal = round(unit_price * qty, 2)
        total_amount += item_subtotal

        order_items_response.append(
            OrderItemResponse(
                product_id=p_id,
                product_name=product["name"],
                quantity=qty,
                unit_price=unit_price,
                subtotal=item_subtotal
            )
        )

    total_amount = round(total_amount, 2)

    # 2. Generate Order ID
    random_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    order_id = f"ORD-{random_suffix}"
    created_at_iso = datetime.utcnow().isoformat()

    # 3. Persist Order into Database
    if use_db:
        try:
            supabase = get_supabase_client()
            # Insert main order
            supabase.table("store_orders").insert({
                "id": order_id,
                "customer_name": payload.customer.name,
                "address": payload.customer.address,
                "email": payload.customer.email,
                "phone": payload.customer.phone,
                "total": total_amount,
                "status": "processing",
                "created_at": created_at_iso
            }).execute()

            # Insert order items & update product stock
            for item in payload.items:
                supabase.table("store_order_items").insert({
                    "order_id": order_id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "unit_price": db_products_map[item.product_id]["price"]
                }).execute()

                # Deduct stock
                new_stock = db_products_map[item.product_id]["stock"] - item.quantity
                supabase.table("store_products").update({"stock": new_stock}).eq("id", item.product_id).execute()

            logger.info(f"🛒 Store order '{order_id}' persisted successfully to DB. Total: ${total_amount}")
        except Exception as e:
            logger.error(f"❌ Failed to persist store order '{order_id}' to Supabase: {e}")
    else:
        # Deduct in fallback memory array
        for item in payload.items:
            if item.product_id in db_products_map:
                db_products_map[item.product_id]["stock"] -= item.quantity

    # 4. Dispatch Order Confirmation Email
    try:
        items_dict_list = [item.dict() for item in order_items_response]
        send_order_confirmation_email(
            customer_name=payload.customer.name,
            customer_email=payload.customer.email,
            order_id=order_id,
            total=total_amount,
            items=items_dict_list
        )
    except Exception as email_err:
        logger.error(f"⚠️ Failed to dispatch order confirmation email: {email_err}")

    return OrderResponse(

        status="success",
        order_id=order_id,
        customer=payload.customer,
        items=order_items_response,
        total=total_amount,
        created_at=created_at_iso
    )
