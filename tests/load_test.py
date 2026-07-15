"""
ACAS v2 - Load Testing Suite
Industrial deployment requirement: Load test with 1000 concurrent users

Usage:
    # Install locust
    pip install locust

    # Run load test
    locust -f tests/load_test.py --host=http://localhost:8000 --users=1000 --spawn-rate=10 --run-time=5m
"""

import random
import json
from locust import HttpUser, task, between


class ACASUser(HttpUser):
    """Simulate real user behavior"""

    wait_time = between(1, 3)  # Think time between requests

    def on_start(self):
        """Login before starting"""
        # Register or login
        self.email = f"loadtest_{random.randint(1, 100000)}@example.com"
        self.password = "TestPass123!"

        # Try to register
        response = self.client.post("/api/auth/register", json={
            "email": self.email,
            "password": self.password,
            "name": f"Load Test User {random.randint(1, 1000)}"
        })

        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
        else:
            # User might already exist, try login
            response = self.client.post("/api/auth/login", data={
                "username": self.email,
                "password": self.password
            })
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
            else:
                self.token = None

        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(10)
    def health_check(self):
        """Health check endpoint (most frequent)"""
        self.client.get("/health")

    @task(5)
    def readiness_check(self):
        """Readiness check"""
        self.client.get("/ready")

    @task(3)
    def get_user_profile(self):
        """Get current user profile"""
        if self.token:
            self.client.get("/api/users/me", headers=self.headers)

    @task(2)
    def update_user_profile(self):
        """Update user profile"""
        if self.token:
            self.client.patch("/api/users/me",
                json={"name": f"Updated User {random.randint(1, 1000)}"},
                headers=self.headers
            )

    @task(2)
    def analyze_sentiment(self):
        """Analyze sentiment (ML endpoint)"""
        if self.token:
            texts = [
                "This product is amazing!",
                "Terrible experience, would not recommend.",
                "It's okay, nothing special.",
                "Best purchase ever!",
                "Waste of money."
            ]
            self.client.post("/api/sentiment/analyze",
                json={"text": random.choice(texts)},
                headers=self.headers
            )

    @task(1)
    def get_insights(self):
        """Get brand insights"""
        if self.token:
            self.client.get("/api/insights",
                params={"brand": "TestBrand", "limit": 10},
                headers=self.headers
            )

    @task(1)
    def create_api_key(self):
        """Create API key"""
        if self.token:
            response = self.client.post("/api/auth/api-keys",
                json={"name": f"load_test_key_{random.randint(1, 1000)}"},
                headers=self.headers
            )
            if response.status_code == 200:
                data = response.json()
                # Don't forget to delete it later
                self.client.delete(f"/api/auth/api-keys/{data.get('id')}", headers=self.headers)


class HighConcurrencyUser(HttpUser):
    """High concurrency scenario (stress test)"""

    wait_time = between(0.1, 0.5)  # Fast requests

    @task
    def health_check(self):
        """Rapid health checks"""
        self.client.get("/health")

    @task
    def login_attempt(self):
        """Rapid login attempts (test rate limiting)"""
        self.client.post("/api/auth/login", data={
            "username": f"user_{random.randint(1, 1000)}@example.com",
            "password": "wrong_password"
        })


# Load test configuration
class LoadTestConfig:
    """Configuration for different load test scenarios"""

    # Scenario 1: Normal load (100 users, 10 min)
    NORMAL_LOAD = {
        "users": 100,
        "spawn_rate": 10,
        "run_time": "10m"
    }

    # Scenario 2: High load (500 users, 5 min)
    HIGH_LOAD = {
        "users": 500,
        "spawn_rate": 20,
        "run_time": "5m"
    }

    # Scenario 3: Spike test (1000 users, 1 min)
    SPIKE = {
        "users": 1000,
        "spawn_rate": 100,
        "run_time": "1m"
    }

    # Scenario 4: Soak test (200 users, 1 hour)
    SOAK = {
        "users": 200,
        "spawn_rate": 5,
        "run_time": "1h"
    }


if __name__ == "__main__":
    import subprocess
    import sys

    # Run different scenarios
    scenarios = [
        ("Normal Load", LoadTestConfig.NORMAL_LOAD),
        ("High Load", LoadTestConfig.HIGH_LOAD),
        ("Spike Test", LoadTestConfig.SPIKE),
        ("Soak Test", LoadTestConfig.SOAK),
    ]

    for name, config in scenarios:
        print(f"\n{'='*60}")
        print(f"Running: {name}")
        print(f"{'='*60}")
        print(f"Users: {config['users']}, Spawn Rate: {config['spawn_rate']}, Run Time: {config['run_time']}")

        cmd = [
            "locust",
            "-f", __file__,
            "--host=http://localhost:8000",
            f"--users={config['users']}",
            f"--spawn-rate={config['spawn_rate']}",
            f"--run-time={config['run_time']}",
            "--headless",
            "--html=load_test_report.html"
        ]

        subprocess.run(cmd)
        print(f"\n{name} completed. Report saved to load_test_report.html")
