"""End-to-end verification of P1 fixes"""
import requests
import json

s = requests.Session()
base = "http://localhost:8000"
results = []

def test(name, ok, detail=""):
    status = "✅" if ok else "❌"
    msg = f"{status} {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append(ok)

# 1. Register
try:
    r = s.post(f"{base}/auth/register", json={
        "email": "p1_verify@example.com",
        "password": "VerifyTest123!",
        "name": "Verify",
        "company": "TestCo"
    })
    test("Register", r.status_code == 201, f"email={r.json().get('email', 'ERR')}")
except Exception as e:
    test("Register", False, str(e))

# 2. Login
try:
    r = s.post(f"{base}/auth/login", json={
        "email": "p1_verify@example.com",
        "password": "VerifyTest123!"
    })
    token = r.json()["access_token"]
    test("Login", r.status_code == 200, "got token")
except Exception as e:
    test("Login", False, str(e))
    exit(1)

headers_jwt = {"Authorization": f"Bearer {token}"}

# 3. JWT auth /me
try:
    r = s.get(f"{base}/auth/me", headers=headers_jwt)
    d = r.json()
    test("JWT /me", r.status_code == 200, f"name={d.get('name', 'ERR')}")
except Exception as e:
    test("JWT /me", False, str(e))

# 4. Create test API key
test_key = ""
try:
    r = s.post(f"{base}/auth/api-keys",
               params={"name": "audit-test-key", "test": True},
               headers=headers_jwt)
    d = r.json()
    test("Create API key (test)", r.status_code == 200,
         f"id={d.get('id', 'ERR')}, prefix={d.get('key', '')[:8]}")
    test_key = d.get("key", "")
except Exception as e:
    test("Create API key (test)", False, str(e))

# 5. Auth via API key
if test_key:
    headers_ak = {"Authorization": f"Bearer {test_key}"}
    try:
        r = s.get(f"{base}/auth/me", headers=headers_ak)
        d = r.json()
        test("API Key auth", r.status_code == 200,
             f"method={d.get('auth_method', 'ERR')}, name={d.get('name', 'ERR')}")
    except Exception as e:
        test("API Key auth", False, str(e))

    # 6. Forecast categories via API key
    try:
        r = s.get(f"{base}/forecast/categories", headers=headers_ak)
        d = r.json()
        test("Forecast categories", r.status_code == 200,
             f"{len(d.get('categories', []))} cats, {len(d.get('regions', []))} regions")
    except Exception as e:
        test("Forecast categories", False, str(e))

    # 7. Intelligence alerts via API key
    try:
        r = s.get(f"{base}/intelligence/alerts", headers=headers_ak, timeout=5)
        test("Intelligence alerts", r.status_code == 200, f"{len(r.json())} alerts")
    except Exception as e:
        test("Intelligence alerts", False, str(e))
else:
    test("API Key auth", False, "no key created")
    test("Forecast categories", False, "skipped")
    test("Intelligence alerts", False, "skipped")

# 8. Health
try:
    r = s.get(f"{base}/health")
    test("Health", r.status_code == 200, r.json().get("status", "ERR"))
except Exception as e:
    test("Health", False, str(e))

# 9. Metrics
try:
    r = s.get(f"{base}/metrics")
    test("Metrics", r.status_code == 200)
except Exception as e:
    test("Metrics", False, str(e))

# 10. List API keys
try:
    r = s.get(f"{base}/auth/api-keys", headers=headers_jwt)
    d = r.json()
    test("List API keys", r.status_code == 200, f"{len(d.get('keys', []))} keys")
except Exception as e:
    test("List API keys", False, str(e))

# Summary
print(f"\n{'='*50}")
passed = sum(results)
total = len(results)
print(f"Results: {passed}/{total} passed")
if passed == total:
    print("ALL TESTS PASSED ✅")
else:
    print(f"FAILURES: {total - passed}")
