"""Vector retriever module for Nivaran AI RAG pipeline.

Ported from Node.js prototype (`index.js` lines 68-87 and `seed.js` lines 27-44).
Original logic:
- Gemini API (`gemini-embedding-001`) with 768-dim output.
- Supabase pgvector cosine similarity search (`1 - (embedding <=> query_vec)`).
"""

import logging
from typing import List, Dict, Any, Tuple
import google.genai as genai
from src.config import (
    GEMINI_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    SIMILARITY_THRESHOLD,
)
from src.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Initialize Gemini Client for embeddings
_gemini_client = None


def get_gemini_client():
    """Initializes and returns Google GenAI client instance."""
    global _gemini_client
    if _gemini_client is None and GEMINI_API_KEY:
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def generate_embedding(text: str) -> List[float]:
    """Generates a 768-dimensional vector embedding using Google Gemini API.

    Ported from `index.js` lines 68-74:
    ```js
    const embeddingResponse = await ai.models.embedContent({
        model: 'gemini-embedding-001',
        contents: incomingMsg,
        config: { outputDimensionality: 768 },
    });
    ```
    """
    try:
        client = get_gemini_client()
        if not client:
            logger.error("Gemini API key missing. Returning dummy zero vector.")
            return [0.0] * EMBEDDING_DIM

        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config={"output_dimensionality": EMBEDDING_DIM},
        )
        
        # Handle embedding structure across sdk versions
        if hasattr(response, "embedding") and response.embedding:
            return response.embedding.values
        elif hasattr(response, "embeddings") and response.embeddings:
            return response.embeddings[0].values
        
        raise ValueError("Could not extract values from Gemini embedding response")
    except Exception as e:
        logger.error(f"❌ Gemini embedding generation failed: {e}")
        # Fallback to empty list or zero vector in case of error
        return [0.0] * EMBEDDING_DIM


def retrieve_context(
    query_text: str,
    match_threshold: float = SIMILARITY_THRESHOLD,
    match_count: int = 3
) -> Tuple[List[Dict[str, Any]], float]:
    """Queries Supabase pgvector database using cosine similarity.

    Ported from `index.js` lines 76-88:
    ```sql
    SELECT id, content, metadata, 1 - (embedding <=> $1::vector) AS similarity
    FROM documentation
    WHERE 1 - (embedding <=> $1::vector) >= $2
    ORDER BY similarity DESC
    LIMIT $3
    ```

    Returns:
        Tuple containing:
        - List of matching document dicts with keys (id, content, metadata, similarity).
        - Maximum similarity score found (0.0 if no matches).
    """
    logger.info(f"🔍 Generating vector embedding for query: '{query_text[:50]}...'")
    query_vector = generate_embedding(query_text)

    try:
        supabase = get_supabase_client()

        # Call Supabase RPC stored procedure 'match_documentation' or vector query
        rpc_params = {
            "query_embedding": query_vector,
            "match_threshold": match_threshold,
            "match_count": match_count
        }

        # Attempt RPC call; if stored proc not created yet, handle fallback gracefully
        response = supabase.rpc("match_documentation", rpc_params).execute()
        documents = response.data or []

        max_similarity = 0.0
        if documents:
            max_similarity = max(doc.get("similarity", 0.0) for doc in documents)
            logger.info(f"📚 Found {len(documents)} matching document(s). Max similarity: {max_similarity:.4f}")
        else:
            logger.warning("❓ No matching documents met the similarity threshold.")

        return documents, max_similarity

    except Exception as e:
        logger.error(f"❌ Error querying pgvector in Supabase: {e}")
        # Return empty list and zero similarity score as fallback
        return [], 0.0


def get_user_active_orders(telegram_id: int) -> List[Dict[str, Any]]:
    """Retrieves active orders linked to user's email (from store_orders) or telegram_id.

    Args:
        telegram_id: Telegram user ID.

    Returns:
        List of order dictionaries with product details.
    """
    if not telegram_id or telegram_id <= 0:
        return []

    try:
        supabase = get_supabase_client()
        # 1. Check if user has email set in users table
        user_res = supabase.table("users").select("email").eq("telegram_id", telegram_id).execute()
        user_email = user_res.data[0].get("email") if user_res.data else None

        if user_email:
            # Query store_orders by email
            so_res = (
                supabase.table("store_orders")
                .select("*")
                .eq("email", user_email.strip().lower())
                .order("created_at", desc=True)
                .execute()
            )
            store_orders = so_res.data or []
            if store_orders:
                for order in store_orders:
                    items_res = (
                        supabase.table("store_order_items")
                        .select("quantity, unit_price, store_products(name)")
                        .eq("order_id", order["id"])
                        .execute()
                    )
                    order["items"] = items_res.data or []
                return store_orders

        # Fallback query on legacy orders table
        response = (
            supabase.table("orders")
            .select("id, status, created_at, products(name, price)")
            .eq("user_id", telegram_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"❌ Error fetching active orders for telegram_id={telegram_id}: {e}")
        return []

