import heapq
import threading
import time
from typing import Dict, Any, List, Tuple

class QueueManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._heap: List[Tuple[float, float, str]] = []  # (-urgency, timestamp, ticket_id)
        self._store: Dict[str, Any] = {}  # ticket_id -> ticket object

    def push(self, ticket):
        with self._lock:
            # use negative urgency for max-heap
            heapq.heappush(self._heap, (-ticket.urgency, time.time(), ticket.id))
            self._store[ticket.id] = ticket

    def pop(self):
        with self._lock:
            if not self._heap:
                return None
            _, _, ticket_id = heapq.heappop(self._heap)
            return self._store.pop(ticket_id, None)

    def peek_all(self):
        with self._lock:
            # return list of tickets ordered by urgency
            ordered = sorted(self._heap)
            return [self._store[item[2]] for item in ordered if item[2] in self._store]

queue_manager = QueueManager()

