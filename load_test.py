#!/usr/bin/env python3
"""
ACAS v2 负载测试
使用 locust 模拟生产并发量
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from locust import HttpUser, task, between
import random
import json


class ACASUser(HttpUser):
    """模拟 ACAS 系统用户行为"""
    
    # 等待时间：1-5秒之间随机（模拟真实用户行为）
    wait_time = between(1, 5)
    
    # 主机地址（通过 --host 参数覆盖）
    host = "http://localhost:8000"
    
    def on_start(self):
        """每个虚拟用户启动时执行一次"""
        # 模拟用户登录
        self.login()
    
    def login(self):
        """用户登录"""
        response = self.client.post(
            "/auth/login",
            json={
                "username": f"user{random.randint(1, 100)}@example.com",
                "password": "testpassword123"
            },
            catch_response=True
        )
        if response.status_code == 200:
            self.token = response.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            # 如果登录失败（可能没有测试用户），使用模拟 token
            self.token = None
            self.headers = {}
    
    @task(10)
    def check_health(self):
        """健康检查 - 权重 10（最高频）"""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")
    
    @task(5)
    def get_intelligence(self):
        """获取情报数据 - 权重 5"""
        with self.client.get(
            "/api/v1/intelligence",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 401, 403]:
                response.success()
            else:
                response.failure(f"Get intelligence failed: {response.status_code}")
    
    @task(3)
    def get_forecast(self):
        """获取预测数据 - 权重 3"""
        with self.client.get(
            "/api/v1/forecast",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 401, 403]:
                response.success()
            else:
                response.failure(f"Get forecast failed: {response.status_code}")
    
    @task(2)
    def get_user_profile(self):
        """获取用户资料 - 权重 2"""
        with self.client.get(
            "/api/v1/users/me",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 401, 403]:
                response.success()
            else:
                response.failure(f"Get user profile failed: {response.status_code}")
    
    @task(1)
    def create_analysis_request(self):
        """创建分析请求 - 权重 1（最低频，模拟重操作）"""
        with self.client.post(
            "/api/v1/intelligence/analyze",
            headers=self.headers,
            json={
                "commodity": random.choice(["wheat", "corn", "coffee", "cocoa"]),
                "region": random.choice(["east-africa", "west-africa", "southern-africa"]),
                "time_range": "30d"
            },
            catch_response=True
        ) as response:
            if response.status_code in [200, 201, 401, 403, 429]:
                response.success()
            else:
                response.failure(f"Create analysis request failed: {response.status_code}")


class ACASAdminUser(HttpUser):
    """模拟管理员用户（低频重载请求）"""
    
    wait_time = between(5, 15)
    host = "http://localhost:8000"
    
    def on_start(self):
        """管理员登录"""
        response = self.client.post(
            "/auth/login",
            json={
                "username": "admin@example.com",
                "password": "adminpassword123"
            },
            catch_response=True
        )
        if response.status_code == 200:
            self.token = response.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.headers = {}
    
    @task(5)
    def check_system_health(self):
        """系统健康检查"""
        self.client.get("/health", headers=self.headers)
    
    @task(2)
    def get_system_metrics(self):
        """获取系统指标"""
        self.client.get("/metrics", headers=self.headers)
    
    @task(1)
    def run_database_query(self):
        """执行数据库查询（模拟重操作）"""
        self.client.get("/api/v1/admin/db-stats", headers=self.headers)


# 自定义负载形状（可选）
from locust import LoadTestShape


class ACASLoadShape(LoadTestShape):
    """
    自定义负载曲线：
    - 0-5分钟：逐步增加到 100 用户
    - 5-15分钟：保持 100 用户（稳态）
    - 15-20分钟：增加到 500 用户（压力测试）
    - 20-25分钟：保持 500 用户（峰值）
    - 25-30分钟：逐步降低到 0（冷却）
    """
    
    stages = [
        {"duration": 300, "users": 100, "spawn_rate": 10},   # 0-5min: 升到 100
        {"duration": 900, "users": 100, "spawn_rate": 10},   # 5-15min: 保持 100
        {"duration": 1200, "users": 500, "spawn_rate": 20},  # 15-20min: 升到 500
        {"duration": 1500, "users": 500, "spawn_rate": 20},  # 20-25min: 保持 500
        {"duration": 1800, "users": 0, "spawn_rate": 50},    # 25-30min: 降到 0
    ]
    
    def tick(self):
        run_time = self.get_run_time()
        
        for stage in self.stages:
            if run_time < stage["duration"]:
                return stage["users"], stage["spawn_rate"]
        
        return None


if __name__ == "__main__":
    import subprocess
    import sys
    
    # 直接运行 locust（供调试用）
    print("Starting Locust load test...")
    print("Open http://localhost:8089 to monitor the test")
    print("Or run headless mode:")
    print("  locust -f load_test.py --host=http://localhost:8000 --users 100 --spawn-rate 10 --run-time 5m --headless")
    
    subprocess.run([
        "locust",
        "-f", __file__,
        "--host=http://localhost:8000",
        "--users=100",
        "--spawn-rate=10",
        "--run-time=5m",
        "--headless",
        "--print-stats",
        "--csv=load_test_results"
    ])
