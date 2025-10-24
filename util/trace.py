import json, os, time, threading

class Trace:
    _lock = threading.Lock()

    def __init__(self, path: str, rotate_mb: int = 20):
        self.path = path
        self.rotate_bytes = int(rotate_mb) * 1024 * 1024
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _rotate(self):
        try:
            if os.path.exists(self.path) and os.path.getsize(self.path) >= self.rotate_bytes:
                ts = time.strftime("%Y%m%d-%H%M%S")
                # rotación simple: copia y limpia (sin gzip para simplicidad)
                os.replace(self.path, f"{self.path}.{ts}")
        except Exception:
            pass

    def log(self, kind: str, **payload):
        rec = {"ts": time.time(), "kind": kind, **payload}
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock:
            self._rotate()
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
