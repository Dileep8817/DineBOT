# RAG: chunk restaurant data, embed with OpenAI, store in Chroma, retrieve at chat time.

import json
import logging
import os
import re

from dotenv import load_dotenv
load_dotenv()

from config import DATA_DIR

logger = logging.getLogger(__name__)

# Same validation as menu_services to avoid path traversal
RESTAURANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "chroma_data")
COLLECTION_NAME = "restaurant_chunks"
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "8"))
EMBEDDING_BATCH_SIZE = 100


def _validate_restaurant_id(restaurant_id: str) -> None:
    if not restaurant_id or not RESTAURANT_ID_PATTERN.match(restaurant_id):
        raise ValueError("restaurant_id must be 1-64 chars: letters, numbers, underscore, hyphen only")


def _get_openai_client():
    from services.llm_service import get_client
    return get_client()


def get_embedding(text: str):
    """Single text -> vector."""
    client = _get_openai_client()
    r = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=text.strip() or " ")
    return r.data[0].embedding


def get_embeddings_batch(texts: list):
    """Batch of texts -> list of vectors. OpenAI accepts many inputs in one call."""
    if not texts:
        return []
    client = _get_openai_client()
    # Clean and avoid empty
    inputs = [t.strip() or " " for t in texts]
    r = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=inputs)
    # Preserve order by index
    by_index = {d.index: d.embedding for d in r.data}
    return [by_index[i] for i in range(len(texts))]


def _chunk_restaurant(restaurant_id: str):
    """Load menu, info, specials, hours and return list of (text, metadata)."""
    _validate_restaurant_id(restaurant_id)
    base = str(DATA_DIR / restaurant_id)
    if not os.path.isdir(base):
        return []

    chunks = []
    # Menu: one chunk per item
    menu_path = os.path.join(base, "menu.json")
    if os.path.isfile(menu_path):
        with open(menu_path) as f:
            menu = json.load(f)
        for i, item in enumerate(menu.get("items", [])):
            name = item.get("name", "")
            price = item.get("price", "")
            desc = item.get("description", "")
            dietary = ", ".join(item.get("dietary", [])) or "none"
            allergens = ", ".join(item.get("allergens", [])) or "none"
            text = f"Restaurant {restaurant_id}. Menu item: {name} — ${price}. {desc}. Dietary: {dietary}. Allergens: {allergens}."
            chunks.append((text, {"restaurant_id": restaurant_id, "source": "menu", "index": i}))

    # Info: one chunk
    info_path = os.path.join(base, "info.json")
    if os.path.isfile(info_path):
        with open(info_path) as f:
            info = json.load(f)
        parts = [f"Restaurant: {restaurant_id}. {info.get('name', '')}. {info.get('description', '')}"]
        parts.append(f"Address: {info.get('address', '')}. Phone: {info.get('phone', '')}. Email: {info.get('email', '')}.")
        if info.get("policies"):
            parts.append(f"Policies: {info.get('policies', '')}")
        if info.get("delivery_available"):
            parts.append(f"Delivery: yes, fee ${info.get('delivery_fee')}, minimum ${info.get('delivery_minimum')}.")
        if info.get("pickup_available"):
            parts.append("Pickup: yes.")
        text = " ".join(parts)
        chunks.append((text, {"restaurant_id": restaurant_id, "source": "info"}))

    # Specials: one chunk per special + ongoing
    specials_path = os.path.join(base, "specials.json")
    if os.path.isfile(specials_path):
        with open(specials_path) as f:
            specials = json.load(f)
        hh = specials.get("happy_hour")
        if isinstance(hh, dict) and (hh.get("when") or hh.get("details")):
            text = (
                f"Restaurant {restaurant_id}. Happy hour: {hh.get('when', '')} — {hh.get('details', '')}"
            )
            chunks.append((text, {"restaurant_id": restaurant_id, "source": "specials_happy_hour"}))
        for i, s in enumerate(specials.get("daily_specials", [])):
            text = f"Restaurant {restaurant_id}. Daily special ({s.get('day', '')}): {s.get('title', '')} — {s.get('description', '')} ({s.get('discount', '')})"
            chunks.append((text, {"restaurant_id": restaurant_id, "source": "specials", "index": i}))
        for i, o in enumerate(specials.get("ongoing", [])):
            text = f"Restaurant {restaurant_id}. Ongoing: {o.get('title', '')} — {o.get('description', '')} ({o.get('valid', '')})"
            chunks.append((text, {"restaurant_id": restaurant_id, "source": "specials_ongoing", "index": i}))

    # Hours: one chunk
    hours_path = os.path.join(base, "hours.json")
    if os.path.isfile(hours_path):
        with open(hours_path) as f:
            hours = json.load(f)
        lines = [f"{k}: {v}" for k, v in hours.items()]
        text = f"Restaurant {restaurant_id}. Hours: " + "; ".join(lines)
        chunks.append((text, {"restaurant_id": restaurant_id, "source": "hours"}))

    return chunks


_chroma_client = None
_collection = None
def _get_collection():
    """Return the Chroma collection, creating the client and collection once and reusing them"""
    global _chroma_client, _collection
    if _collection is None:
        import chromadb
        from chromadb.config import Settings
        _chroma_client = chromadb.PersistentClient(
            path = CHROMA_PERSIST_DIR,
            settings = Settings(anonymized_telemetry=False)
        )
        _collection = _chroma_client.get_or_create_collection(
            name = COLLECTION_NAME,
            metadata = {"description": "Restaurant menu, info, specials, hours for RAG"}
        )
    return _collection

def index_restaurant(restaurant_id: str) -> int:
    """Chunk restaurant data, embed, upsert into Chroma. Returns number of chunks indexed."""
    chunks_with_meta = _chunk_restaurant(restaurant_id)
    if not chunks_with_meta:
        logger.warning("No chunks for restaurant_id=%s", restaurant_id)
        return 0

    # chunks the data
    texts = [t for t, _ in chunks_with_meta]
    metadatas = [m for _, m in chunks_with_meta]
    ids = [f"{restaurant_id}_{metadatas[i].get('source', '')}_{i}" for i in range(len(texts))]

    # Delete existing docs for this restaurant so we can re-index
    try:
        coll = _get_collection()
        coll.delete(where={"restaurant_id": restaurant_id})
    except Exception as e:
        logger.warning("Could not delete existing chunks for %s: %s", restaurant_id, e)

    # Embed in batches and add
    for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch_texts = texts[start : start + EMBEDDING_BATCH_SIZE]
        batch_metadatas = metadatas[start : start + EMBEDDING_BATCH_SIZE]
        batch_ids = ids[start : start + EMBEDDING_BATCH_SIZE]
        embeddings = get_embeddings_batch(batch_texts)
        coll = _get_collection()
        coll.add(ids=batch_ids, embeddings=embeddings, documents=batch_texts, metadatas=batch_metadatas)

    logger.info("RAG indexed restaurant_id=%s chunks=%d", restaurant_id, len(texts))
    return len(texts)


def index_all_restaurants() -> int:
    """Discover data/<restaurant_id>/ and index each. Returns total chunks indexed."""
    data_dir = str(DATA_DIR)
    if not os.path.isdir(data_dir):
        logger.warning("RAG: no data/ directory, skipping index")
        return 0
    total = 0
    for name in os.listdir(data_dir):
        path = os.path.join(data_dir, name)
        if os.path.isdir(path) and RESTAURANT_ID_PATTERN.match(name):
            try:
                total += index_restaurant(name)
            except Exception as e:
                logger.exception("RAG index failed for %s: %s", name, e)
    return total


def retrieve(restaurant_id: str, query: str, top_k: int = None) -> list:
    """Return list of relevant chunk texts for the query. Empty if RAG not available or no index."""
    top_k = top_k or RAG_TOP_K
    try:
        _validate_restaurant_id(restaurant_id)
        query_embedding = get_embedding(query) # converts user query to a embedding
        coll = _get_collection()
        results = coll.query( # searches Chroma database for similar chunks
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"restaurant_id": restaurant_id},
        )
        if results and results.get("documents") and results["documents"][0]:
            return results["documents"][0]
        return [] # returns the most relevant chunks
    except ValueError:
        return []
    except Exception as e:
        logger.debug("RAG retrieve failed: %s", e)
        return []
