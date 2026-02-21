import time
from Main import process_ticket

def send_ticket(text, priority):
    """Helper to send tasks to the Celery broker"""
    print(f"[{priority.upper()}] Pushing ticket to queue -> '{text}'")
    # Route queue using apply_async
    process_ticket.apply_async(args=[text, priority], queue=priority)

def simulate_normal():
    print("\n" + "="*50)
    print("SIMULATING NORMAL TRAFFIC (Unrelated Tickets)")
    print("="*50)
    tickets = [
        ("User cannot login to the dashboard", "high"),
        ("Request for a new laptop", "low"),
        ("Payment gateway timeout sporadically", "medium"),
        ("How to reset password?", "low"),
        ("Database schema update for next release", "medium")
    ]
    
    for text, priority in tickets:
        send_ticket(text, priority)
        time.sleep(1)

def simulate_flash_flood():
    print("\n" + "="*50)
    print("SIMULATING FLASH FLOOD (Ticket Storm)")
    print("="*50)
    
    # 15 highly similar tickets (same core meaning with slight variations)
    flood_text = "Database connection refused on production DB DB01"
    
    # Send 15 similar tickets rapidly
    for i in range(35):
        # Add slight variation to prove Semantic Embeddings check meaning, not just exact match
        text = flood_text + f" (Instance {i})"
        send_ticket(text, "high")
        
        # very small delay so order is maintained in queue but it's a "burst"
        time.sleep(0.1)

if __name__ == "__main__":
    simulate_normal()
    
    print("\nWaiting 5 seconds before triggering flash flood to let workers catch up...\n")
    time.sleep(5)
    
    simulate_flash_flood()
