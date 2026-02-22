import os
import time
import uuid
import numpy as np
from celery import Celery
from sentence_transformers import SentenceTransformer
import redis
from dotenv import load_dotenv

load_dotenv()

# We will use Redis as the Celery broker and backend
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
HF_LOCAL_ONLY = os.getenv("HF_LOCAL_ONLY", "0").strip().lower() in {"1", "true", "yes"}
M3_MODEL_ID = os.getenv("M3_MODEL_ID", "all-MiniLM-L6-v2")
M3_MODEL_PATH = os.getenv("M3_MODEL_PATH", "").strip()

# Initialize Celery explicitly naming the app 'Main' to match this file
app = Celery('Main', broker=REDIS_URL, backend=REDIS_URL)

# Configure Celery routing
app.conf.task_default_queue = 'default'
app.conf.task_routes = {
    'Main.process_ticket': {'queue': 'default'},
}

# The user requested semantic deduplication using 'all-MiniLM-L6-v2'
print("Loading SentenceTransformer model...")
model_ref = M3_MODEL_PATH if M3_MODEL_PATH else M3_MODEL_ID
model = SentenceTransformer(model_ref, local_files_only=HF_LOCAL_ONLY)
print("Model loaded.")

# Connect to Redis to hold the 5-minute rolling window state
redis_client = redis.Redis.from_url(REDIS_URL)


def cosine_similarity(v1, v2):
    """Calculates the Cosine Similarity between two vectors"""
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0
    return dot_product / (norm_v1 * norm_v2)


@app.task(name="Main.process_ticket")
def process_ticket(ticket_text, priority):
    """
    Celery task to process incoming tickets and perform Semantic Deduplication.
    Uses Redis to share state across potential multiple workers.
    """
    ticket_id = str(uuid.uuid4())
    current_time = time.time()
    
    # 1. Generate Embedding
    embedding = model.encode(ticket_text)
    
    # 2. Clean up old tickets (Maintain a 5-minute / 300 second rolling window)
    cutoff_time = current_time - 300
    old_ticket_ids = redis_client.zrangebyscore('recent_tickets', 0, cutoff_time)
    
    if old_ticket_ids:
        # Remove from sorted set
        redis_client.zremrangebyscore('recent_tickets', 0, cutoff_time)
        # Remove the actual hash data
        redis_client.delete(*[f"ticket:{tid.decode('utf-8')}" for tid in old_ticket_ids])
    
    # 3. Fetch all recent ticket embeddings to calculate similarities
    recent_ticket_ids = redis_client.zrange('recent_tickets', 0, -1)
    
    similar_count = 0
    for tid_bytes in recent_ticket_ids:
        tid = tid_bytes.decode('utf-8')
        hist_emb_bytes = redis_client.hget(f"ticket:{tid}", 'embedding')
        
        if hist_emb_bytes:
            # Convert bytes back to numpy array
            hist_emb = np.frombuffer(hist_emb_bytes, dtype=np.float32)
            
            # Calculate Cosine Similarity
            sim = cosine_similarity(embedding, hist_emb)
            
            # Condition: similarity > 0.9
            if sim > 0.9:
                similar_count += 1
                
    # 4. Deduplicate if Flash-Flood condition is met (> 10 similar tickets)
    print("-" * 50)
    if similar_count >= 10:
        print(f"[MASTER INCIDENT CREATED] Flash-flood detected! Suppressing duplicate alert.")
        print(f"Priority: {priority.upper()} | Ticket: '{ticket_text}'")
        print(f"Similarity: > 0.9 with {similar_count} recent tickets in the last 5 minutes.")
    else:
        print(f"[ALERT] Processed new ticket: '{ticket_text}'")
        print(f"Priority: {priority.upper()} | Similar past tickets: {similar_count}")
    print("-" * 50)
        
    # 5. Store this ticket's embedding and text in Redis for the rolling window
    redis_client.zadd('recent_tickets', {ticket_id: current_time})
    redis_client.hset(f"ticket:{ticket_id}", 'text', ticket_text)
    redis_client.hset(f"ticket:{ticket_id}", 'embedding', embedding.astype(np.float32).tobytes())

    return {"status": "success", "ticket_id": ticket_id, "similar_count": similar_count}

if __name__ == '__main__':
    # When run directly, we can start the worker for convenience
    # Typically you'd run `celery -A Main worker -Q high,medium,low --loglevel=info`
    # On Windows, the default multiprocessing pool can fail, so we use --pool=solo
    app.worker_main(['worker', '-Q', 'high,medium,low', '--loglevel=info', '--pool=solo'])
