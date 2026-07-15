"""
Locust Load Test for ACAS v2 Minimal
Run: locust -f this_file.py --host=http://localhost:8000 --users 10 --spawn-rate 2 --run-time 60s --headless
"""

from locust import HttpUser, task, between
import random

class ACASUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """Login at start"""
        self.token = "mock_token_for_load_testing"
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task(10)
    def health_check(self):
        """Health check (most frequent)"""
        self.client.get("/health")
    
    @task(5)
    def ready_check(self):
        """Readiness probe"""
        self.client.get("/ready")
    
    @task(5)
    def liveness_check(self):
        """Liveness probe"""
        self.client.get("/live")
    
    @task(3)
    def get_user_profile(self):
        """Get current user"""
        self.client.get("/api/users/me", headers=self.headers)
    
    @task(2)
    def analyze_sentiment(self):
        """Sentiment analysis"""
        texts = [
            "This product is amazing!",
            "Terrible experience, would not recommend.",
            "Average quality, nothing special.",
            "Great value for money!",
            "Disappointed with the service."
        ]
        self.client.post(
            "/api/sentiment/analyze",
            json={"text": random.choice(texts)},
            headers=self.headers
        )
    
    @task(1)
    def predict(self):
        """Forecast prediction"""
        self.client.post("/api/forecast/predict", headers=self.headers)
