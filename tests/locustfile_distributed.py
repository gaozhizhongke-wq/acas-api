"""
Distributed Locust Load Test for ACAS v2
Correctly distributes load across 4 worker processes (ports 8000-8003)
"""

from locust import HttpUser, task, between, events
import random

# Worker ports configuration
WORKER_PORTS = [8000, 8001, 8002, 8003]

class ACASDistributedUser(HttpUser):
    """User class with fixed host per instance"""
    wait_time = between(0.5, 2)
    
    def on_start(self):
        """Set fixed host for this user instance"""
        port = random.choice(WORKER_PORTS)
        self.client.base_url = f"http://localhost:{port}"
        self.token = "mock_token_for_load_testing"
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task(15)
    def health_check(self):
        """Health check"""
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
