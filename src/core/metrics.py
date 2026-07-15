"""
In-memory Prometheus metrics tracker for ACAS v2.
Thread-safe, no external dependencies.
"""

import re
import threading
import time
from typing import Dict, Tuple

# Histogram bucket upper bounds (seconds)
HISTOGRAM_BUCKETS = (0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0)


class MetricsTracker:
    """
    Thread-safe in-memory metrics tracker that emits Prometheus text format.

    Tracks:
    - Request count by (method, endpoint, status_code)
    - Request duration histogram per endpoint
    - Active in-flight requests gauge
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {(method, endpoint, status_code): count}
        self._counters: Dict[Tuple[str, str, int], int] = {}
        # {endpoint: {bucket_index: count}} — bucket i counts requests ≤ bucket[i]
        self._histograms: Dict[str, list] = {}
        # Gauge: current number of in-flight requests
        self._active: int = 0

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _generalize_path(path: str) -> str:
        """
        Replace dynamic path segments with placeholders so that e.g.
        /users/42 and /users/abc-123 collapse to the same /users/:id label.
        """
        # Strip trailing slash
        path = path.rstrip("/")
        if not path:
            path = "/"
        # Replace UUIDs (32 hex chars)
        path = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "/:id", path, flags=re.I)
        # Replace bare UUID (no surrounding slashes)
        path = re.sub(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", ":id", path, flags=re.I)
        # Replace integer IDs: /users/123 → /users/:id
        path = re.sub(r"/\d+(/|$)", r"/:id\1", path)
        return path

    def _ensure_histogram(self, endpoint: str) -> list:
        """Return (creating if needed) the histogram counter list for an endpoint."""
        if endpoint not in self._histograms:
            self._histograms[endpoint] = [0] * len(HISTOGRAM_BUCKETS)
        return self._histograms[endpoint]

    def _histogram_bucket_index(self, duration: float) -> int:
        """Return the index of the smallest bucket that covers `duration`."""
        for i, bound in enumerate(HISTOGRAM_BUCKETS):
            if duration <= bound:
                return i
        return len(HISTOGRAM_BUCKETS)  # overflow bucket (beyond last bucket)

    # ── Public API ─────────────────────────────────────────────────────────────

    def inc_active(self) -> None:
        with self._lock:
            self._active += 1

    def dec_active(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)

    def record_request(
        self,
        method: str,
        raw_path: str,
        status_code: int,
        duration: float,
    ) -> None:
        """
        Record a completed request.

        Args:
            method: HTTP method (GET, POST, …)
            raw_path: Original request path (may contain IDs)
            status_code: HTTP response status code
            duration: Elapsed time in seconds
        """
        endpoint = self._generalize_path(raw_path)

        with self._lock:
            # Increment counter
            key = (method, endpoint, status_code)
            self._counters[key] = self._counters.get(key, 0) + 1

            # Update histogram
            hist = self._ensure_histogram(endpoint)
            idx = self._histogram_bucket_index(duration)
            for i in range(idx, len(HISTOGRAM_BUCKETS)):
                hist[i] += 1

    def get_active(self) -> int:
        with self._lock:
            return self._active

    # ── Prometheus exposition format ───────────────────────────────────────────

    def render(self, version: str, environment: str, db_ok: bool, redis_ok: bool) -> str:
        """
        Render all metrics as Prometheus text format.
        Callers inject app-level gauges (info, db, redis) separately.
        """
        lines: list[str] = []

        # ── Info gauge ─────────────────────────────────────────────────────────
        lines.append("# HELP acas_info ACAS application info")
        lines.append("# TYPE acas_info gauge")
        lines.append(f'acas_info{{version="{version}","environment="{environment}"}} 1')

        # ── Database gauge ─────────────────────────────────────────────────────
        lines.append("# HELP acas_database_connected Database connection status (1=up, 0=down)")
        lines.append("# TYPE acas_database_connected gauge")
        lines.append(f"acas_database_connected {1 if db_ok else 0}")

        # ── Redis gauge ────────────────────────────────────────────────────────
        lines.append("# HELP acas_redis_connected Redis connection status (1=up, 0=down)")
        lines.append("# TYPE acas_redis_connected gauge")
        lines.append(f"acas_redis_connected {1 if redis_ok else 0}")

        with self._lock:
            # ── Request counters ────────────────────────────────────────────────
            lines.append("# HELP acas_requests_total Total HTTP requests")
            lines.append("# TYPE acas_requests_total counter")
            for (method, endpoint, status_code), count in sorted(self._counters.items()):
                lines.append(
                    f"acas_requests_total{{"
                    f'method="{method}",'
                    f'endpoint="{endpoint}",'
                    f'status_code="{status_code}"'
                    f"}} {count}"
                )

            # ── Duration histogram ───────────────────────────────────────────────
            lines.append("# HELP acas_request_duration_seconds HTTP request duration in seconds")
            lines.append("# TYPE acas_request_duration_seconds histogram")
            for endpoint, hist in sorted(self._histograms.items()):
                cumulative = 0
                for bound, bucket_count in zip(HISTOGRAM_BUCKETS, hist):
                    cumulative += bucket_count
                    lines.append(
                        f"acas_request_duration_seconds_bucket{{"
                        f'endpoint="{endpoint}",'
                        f'le="{bound}"'
                        f"}} {cumulative}"
                    )
                # +Inf bucket = total count
                total = sum(hist)
                lines.append(f"acas_request_duration_seconds_bucket{{endpoint=\"{endpoint}\",le=\"+Inf\"}} {total}")
                lines.append(f"acas_request_duration_seconds_sum{{endpoint=\"{endpoint}\"}} {0}")  # placeholder — sum not tracked
                lines.append(f"acas_request_duration_seconds_count{{endpoint=\"{endpoint}\"}} {total}")

            # ── Active requests gauge ────────────────────────────────────────────
            lines.append("# HELP acas_requests_active Current number of in-flight HTTP requests")
            lines.append("# TYPE acas_requests_active gauge")
            lines.append(f"acas_requests_active {self._active}")

        return "\n".join(lines) + "\n"


# ── Global singleton (imported throughout the app) ──────────────────────────
metrics_tracker = MetricsTracker()
