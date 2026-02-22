from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import time

@dataclass
class Ticket:
    id: str
    subject: str
    body: str
    customer: str
    category: Optional[str] = None
    urgency: float = 0.0
    status: str = "new"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())

