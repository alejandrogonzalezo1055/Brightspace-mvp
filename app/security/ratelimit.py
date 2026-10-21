"""
Límite de tasa con token bucket [DOC]: cada llamada gasta créditos de la cubeta de la app; si se
acaba, 429. Encabezados [DOC]: X-Rate-Limit-Remaining, X-Request-Cost, X-Rate-Limit-Reset y
Retry-After.

[APROX] Capacidad, ventana y costo por ruta no son públicos: aquí cada llamada cuesta 1 crédito y
la cubeta se rellena por completo en RATE_LIMIT_WINDOW_S segundos.
"""
import math
import threading
import time
from dataclasses import dataclass


@dataclass
class Decision:
    allowed: bool
    remaining: int
    cost: int
    reset_s: int

    def headers(self) -> dict[str, str]:
        result = {
            "X-Rate-Limit-Remaining": str(self.remaining),
            "X-Request-Cost": str(self.cost),
            "X-Rate-Limit-Reset": str(self.reset_s),
        }
        if not self.allowed:
            result["Retry-After"] = str(self.reset_s)
        return result


class TokenBucketLimiter:
    def __init__(self, capacity: int, window_s: int):
        self.capacity = capacity
        self.refill_per_s = capacity / window_s
        self._buckets: dict[str, tuple[float, float]] = {}  # clave -> (créditos, última actualización)
        self._lock = threading.Lock()

    def consume(self, key: str, cost: int = 1) -> Decision:
        with self._lock:
            now = time.monotonic()
            credits, last = self._buckets.get(key, (float(self.capacity), now))
            credits = min(self.capacity, credits + (now - last) * self.refill_per_s)
            allowed = credits >= cost
            if allowed:
                credits -= cost
            self._buckets[key] = (credits, now)
            reset_s = math.ceil((self.capacity - credits) / self.refill_per_s)
            return Decision(allowed=allowed, remaining=int(credits), cost=cost, reset_s=reset_s)
