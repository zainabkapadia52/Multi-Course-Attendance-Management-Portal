import queue
import threading
import json

# One queue per connected client
_clients: list[queue.Queue] = []
_lock = threading.Lock()

def subscribe() -> queue.Queue:
    """Register a new SSE listener. Returns its queue."""
    q = queue.Queue(maxsize=20)
    with _lock:
        _clients.append(q)
    return q

def unsubscribe(q: queue.Queue):
    with _lock:
        if q in _clients:
            _clients.remove(q)

def broadcast(event_type: str, data: dict):
    """Push an event to every connected client."""
    payload = json.dumps({"type": event_type, "data": data})
    dead    = []
    with _lock:
        for q in _clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)  # tab probably closed
    for q in dead:
        unsubscribe(q)