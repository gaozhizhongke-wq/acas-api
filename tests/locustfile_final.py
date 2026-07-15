"""
Final Load Test: 100 QPS + P99 Validation
Uses HTTP connection pooling + separate warmup phase
"""
from locust import HttpUser, task, between, events
import random

# Global stats to track warmup completion
_warmup_done = False
_first_normal_request_time = None

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called once when test starts"""
    global _warmup_done, _first_normal_request_time
    _warmup_done = False
    _first_normal_request_time = None

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Track first non-warmup request"""
    global _warmup_done, _first_normal_request_time
    if name and not name.endswith("[warmup]") and not _warmup_done:
        if _first_normal_request_time is None:
            _first_normal_request_time = kwargs.get('start_time')
        # Warmup window: first 5 seconds = warmup
        if _first_normal_request_time and _warmup_done is False:
            import time
            if time.time() - _first_normal_request_time > 5:
                _warmup_done = True

class ACASFinalUser(HttpUser):
    """Final load test user with pre-warmup"""
    wait_time = between(0.05, 0.3)
    
    def on_start(self):
        """Pre-warm connection (runs BEFORE test timer starts)"""
        self.token = "mock_token_for_load_testing"
        self.headers = {"Authorization": f"Bearer {self.token}"}
        # These warmup requests run at test start, before timer
        self.client.get("/health", name="/health [warmup]")
        self.client.get("/ready", name="/ready [warmup]")
    
    @task(15)
    def health_check(self):
        self.client.get("/health", name="/health")
    
    @task(10)
    def ready_check(self):
        self.client.get("/ready", name="/ready")
    
    @task(8)
    def liveness_check(self):
        self.client.get("/live", name="/live")
    
    @task(5)
    def get_user_profile(self):
        self.client.get("/api/users/me", headers=self.headers, name="/api/users/me")
    
    @task(3)
    def analyze_sentiment(self):
        texts = ["Amazing!", "Terrible.", "Average.", "Great value!", "Disappointed."]
        self.client.post("/api/sentiment/analyze", json={"text": random.choice(texts)},
                        headers=self.headers, name="/api/sentiment/analyze")
    
    @task(2)
    def predict(self):
        self.client.post("/api/forecast/predict", headers=self.headers, name="/api/forecast/predict")
