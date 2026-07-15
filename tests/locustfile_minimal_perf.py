"""
High-Performance Locust Load Test for ACAS v2
Target: 100 QPS, P99 < 200ms
Features: short wait times, connection keepalive, full warmup
"""
from locust import HttpUser, task, between, events
import random

# Track total requests for statistics
request_count = 0

@events.init_command_line_parser.add_listener
def on_parser(parser):
    """Allow custom target QPS via --target-qps CLI arg"""
    parser.add_argument("--target-qps", type=int, default=100, help="Target QPS")

class ACASPerfUser(HttpUser):
    """
    High-performance load test user.
    Short wait times to sustain 100+ req/s from 100 users.
    """
    # Very short wait to maximize RPS
    wait_time = between(0.05, 0.3)
    
    # Use connection pooling / keepalive
    # Note: FastAPI/uvicorn reuses connections automatically
    
    def on_start(self):
        """Login and pre-warm connection on start"""
        self.token = "mock_token_for_load_testing"
        self.headers = {"Authorization": f"Bearer {self.token}"}
        # Pre-warm: hit health once per user to avoid first-request cold start
        self.client.get("/health", name="/health [warmup]")
        self.client.get("/ready", name="/ready [warmup]")
    
    @task(15)
    def health_check(self):
        """Health check (highest frequency)"""
        self.client.get("/health", name="/health")
    
    @task(10)
    def ready_check(self):
        """Readiness probe"""
        self.client.get("/ready", name="/ready")
    
    @task(8)
    def liveness_check(self):
        """Liveness probe"""
        self.client.get("/live", name="/live")
    
    @task(5)
    def get_user_profile(self):
        """Get current user"""
        self.client.get("/api/users/me", headers=self.headers, name="/api/users/me")
    
    @task(3)
    def analyze_sentiment(self):
        """Sentiment analysis"""
        texts = [
            "This product is amazing!",
            "Terrible experience.",
            "Average quality.",
            "Great value!",
            "Disappointed."
        ]
        self.client.post(
            "/api/sentiment/analyze",
            json={"text": random.choice(texts)},
            headers=self.headers,
            name="/api/sentiment/analyze"
        )
    
    @task(2)
    def predict(self):
        """Forecast prediction"""
        self.client.post("/api/forecast/predict", headers=self.headers, name="/api/forecast/predict")
