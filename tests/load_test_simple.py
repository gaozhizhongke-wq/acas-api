from locust import HttpUser, task, between

class ACASUser(HttpUser):
    wait_time = between(1, 2)
    
    def on_start(self):
        # Login
        response = self.client.post("/api/auth/login", 
            data={"username": "test@example.com", "password": "TestPass123!"},
            catch_response=True
        )
        if response.status_code == 200:
            self.token = response.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            # Register first
            self.client.post("/api/auth/register",
                json={"email": "test@example.com", "password": "TestPass123!", "name": "Test User"}
            )
            response = self.client.post("/api/auth/login",
                data={"username": "test@example.com", "password": "TestPass123!"}
            )
            if response.status_code == 200:
                self.token = response.json().get("access_token")
                self.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task(10)
    def health_check(self):
        self.client.get("/health")
    
    @task(5)
    def get_user_profile(self):
        if hasattr(self, 'headers'):
            self.client.get("/api/users/me", headers=self.headers)
    
    @task(3)
    def analyze_sentiment(self):
        if hasattr(self, 'headers'):
            self.client.post("/api/sentiment/analyze",
                json={"text": "This is a test sentiment analysis request"},
                headers=self.headers
            )

# Run with: locust -f load_test_simple.py --host=http://localhost:8000 --users 10 --spawn-rate 2 --run-time 1m --headless
