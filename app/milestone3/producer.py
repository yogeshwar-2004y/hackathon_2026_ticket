import time
from Main import process_ticket

def send_ticket(text, priority, category):
    """Helper to send tasks to the Celery broker"""
    print(f"[{priority.upper()}] Pushing ticket to queue -> '{text}' ({category})")
    # Route queue using apply_async
    process_ticket.apply_async(args=[text, priority, category], queue=priority)

def simulate_normal():
    print("\n" + "="*50)
    print("SIMULATING NORMAL TRAFFIC (Unrelated Tickets)")
    print("="*50)
    tickets = [
        ("User cannot login to the dashboard", "high", "Technical"),
        ("Request for billing statement", "low", "Billing"),
        ("Payment gateway timeout sporadically", "medium", "Billing"),
        ("How to reset password?", "low", "Technical"),
        ("Legal review for new compliance rule", "medium", "Legal")
    ]
    
    for text, priority, category in tickets:
        send_ticket(text, priority, category)
        time.sleep(3)

def simulate_flash_flood():
    print("\n" + "="*50)
    print("SIMULATING FLASH FLOOD (Ticket Storm)")
    print("="*50)
    
    # 15 highly similar tickets (same core meaning with slight variations)
    flood_text = "Database connection refused on production DB DB01"
    
    # Send 35 similar tickets rapidly
    for i in range(20):
        # Add slight variation to prove Semantic Embeddings check meaning, not just exact match
        text = flood_text + f" (Instance {i})"
        send_ticket(text, "high", "Technical")
        
        # very small delay so order is maintained in queue but it's a "burst"
        time.sleep(1)

if __name__ == "__main__":
    simulate_normal()
    
    print("\nWaiting 5 seconds before triggering flash flood to let workers catch up...\n")
    time.sleep(10)
    
    simulate_flash_flood()
