import os
import time
import uuid
import json
import numpy as np
from celery import Celery
from sentence_transformers import SentenceTransformer
import redis
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from app.rest_api.ws_status import publish_status

load_dotenv()

# We will use Redis as the Celery broker and backend
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
HF_LOCAL_ONLY = os.getenv("HF_LOCAL_ONLY", "0").strip().lower() in {"1", "true", "yes"}
M3_MODEL_ID = os.getenv("M3_MODEL_ID", "all-MiniLM-L6-v2")
M3_MODEL_PATH = os.getenv("M3_MODEL_PATH", "").strip()

# Initialize Celery explicitly naming the app 'Main' to match this file. No backend needed for now.
app = Celery('Main', broker=REDIS_URL)

# Configure Celery routing
app.conf.task_default_queue = 'default'
app.conf.broker_transport_options = {
    'queue_order_strategy': 'priority',
}
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
mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = mongo["ticket_router"]
tickets_col = db["tickets"]
agents_col = db["agents"]
DEFAULT_AGENTS = {
    "Agent_A": {"name": "Alice", "skills": {"Technical": 0.9, "Billing": 0.1, "Legal": 0.0}, "active_load": 0},
    "Agent_B": {"name": "Bob", "skills": {"Technical": 0.2, "Billing": 0.8, "Legal": 0.0}, "active_load": 0},
    "Agent_C": {"name": "Charlie", "skills": {"Technical": 0.0, "Billing": 0.2, "Legal": 0.8}, "active_load": 0},
    "Agent_D": {"name": "Dana", "skills": {"Technical": 0.9, "Billing": 0.1, "Legal": 0.0}, "active_load": 0},
}


def cosine_similarity(v1, v2):
    """Calculates the Cosine Similarity between two vectors"""
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0
    return dot_product / (norm_v1 * norm_v2)


def _seed_agents_if_empty():
    try:
        # Avoid count_documents (aggregate command) to reduce auth requirements.
        if agents_col.find_one({}, {"_id": 1}) is not None:
            return
    except PyMongoError:
        # If we can't read agents collection due to auth, caller will fallback.
        return
    try:
        agents_col.insert_many(
            [
                {"_id": "Agent_A", "name": "Alice", "skills": {"Technical": 0.9, "Billing": 0.1, "Legal": 0.0}, "active_load": 0},
                {"_id": "Agent_B", "name": "Bob", "skills": {"Technical": 0.2, "Billing": 0.8, "Legal": 0.0}, "active_load": 0},
                {"_id": "Agent_C", "name": "Charlie", "skills": {"Technical": 0.0, "Billing": 0.2, "Legal": 0.8}, "active_load": 0},
                {"_id": "Agent_D", "name": "Dana", "skills": {"Technical": 0.9, "Billing": 0.1, "Legal": 0.0}, "active_load": 0},
            ]
        )
    except PyMongoError:
        # Not fatal: fallback agent list will be used.
        return


def _get_agents():
    try:
        _seed_agents_if_empty()
        docs = list(agents_col.find({}))
        if not docs:
            return DEFAULT_AGENTS.copy()
        return {
            d["_id"]: {
                "name": d.get("name", d["_id"]),
                "skills": d.get("skills", {}),
                "active_load": int(d.get("active_load", 0)),
            }
            for d in docs
        }
    except PyMongoError:
        return DEFAULT_AGENTS.copy()


def find_best_agent(category, agents):
    """
    Finds the best agent based on highest skill match for the given category.
    If there's a tie, selects the agent with the lowest current workload.
    """
    best_agents = []
    highest_score = -1

    for agent_id, data in agents.items():
        score = data["skills"].get(category, 0)
        
        if score > highest_score:
            highest_score = score
            best_agents = [agent_id]
        elif score == highest_score and score > 0:
            best_agents.append(agent_id)

    if not best_agents:
        return None

    if len(best_agents) == 1:
        return best_agents[0]
        
    # Tie-breaker: least workload
    min_load = float('inf')
    chosen_agent = None
    
    for agent_id in best_agents:
        # Use MongoDB as source of truth for workload.
        current_load = int(agents.get(agent_id, {}).get("active_load", 0))
        if current_load < min_load:
            min_load = current_load
            chosen_agent = agent_id

    return chosen_agent


@app.task(name="Main.process_ticket")
def process_ticket(ticket_text, priority):
    """
    Celery task to process incoming tickets and perform Semantic Deduplication.
    Uses Redis to share state across potential multiple workers.
    """
    payload = {}
    try:
        payload = json.loads(ticket_text) if isinstance(ticket_text, str) else {}
    except Exception:
        payload = {}

    ticket_id = payload.get("ticket_id") or str(uuid.uuid4())
    category = payload.get("category", "Technical")
    current_time = time.time()
    try:
        tickets_col.update_one(
            {"_id": ticket_id},
            {"$set": {"status": "m3_processing", "updated_at": current_time}},
            upsert=True,
        )
        publish_status(ticket_id, "m3_processing")
    except Exception:
        pass
    
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
    assigned_agent = None
    agents = _get_agents()
    if similar_count >= 10:
        print(f"[MASTER INCIDENT CREATED] Flash-flood detected! Suppressing duplicate alert.")
        print(f"Priority: {priority.upper()} | Ticket: '{ticket_text}'")
        print(f"Similarity: > 0.9 with {similar_count} recent tickets in the last 5 minutes.")
    else:
        print(f"[ALERT] Processed new ticket: '{ticket_text}'")
        print(f"Priority: {priority.upper()} | Similar past tickets: {similar_count}")
        
        # Route to the best agent based on simple classification match
        assigned_agent = find_best_agent(category, agents)
        if assigned_agent:
            try:
                agents_col.update_one({"_id": assigned_agent}, {"$inc": {"active_load": 1}})
            except PyMongoError:
                pass
            print(f"[ROUTED] Ticket assigned to {agents[assigned_agent]['name']} (Score: {agents[assigned_agent]['skills'].get(category, 0)})")
        else:
            print("[QUEUED] No suitable agent found for category.")
    print("-" * 50)
        
    # 5. Store this ticket's embedding and text in Redis for the rolling window
    redis_client.zadd('recent_tickets', {ticket_id: current_time})
    redis_client.hset(f"ticket:{ticket_id}", 'text', ticket_text)
    redis_client.hset(f"ticket:{ticket_id}", 'embedding', embedding.astype(np.float32).tobytes())

    result = {"status": "success", "ticket_id": ticket_id, "similar_count": similar_count, "agent": assigned_agent}
    try:
        tickets_col.update_one(
            {"_id": ticket_id},
            {
                "$set": {
                    "status": "resolved",
                    "priority": priority,
                    "similar_count": int(similar_count),
                    "assigned_agent": assigned_agent,
                    "updated_at": time.time(),
                }
            },
            upsert=True,
        )
        publish_status(
            ticket_id,
            "resolved",
            priority=priority,
            similar_count=int(similar_count),
            agent=assigned_agent,
        )
    except Exception:
        pass
    print(f"[FINAL RESULT] {result}\n")
    return result

if __name__ == '__main__':
    # When run directly, we can start the worker for convenience
    # Typically you'd run `celery -A Main worker -Q high,medium,low --loglevel=info`
    # On Windows, the default multiprocessing pool can fail, so we use --pool=solo
    app.worker_main(['worker', '-Q', 'high,medium,low', '--loglevel=info', '--pool=solo'])
