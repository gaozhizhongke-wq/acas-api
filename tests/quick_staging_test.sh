#!/bin/bash
# ACAS v2 - Quick Staging Test Script
# Run this after deploying to staging

set -e

# Configuration
API_URL="${1:-<http://localhost:8000>}"
ADMIN_EMAIL="admin@acas-staging.com"
ADMIN_PASSWORD="AdminPassword123!"

echo "=========================================="
echo "ACAS v2 - Quick Staging Validation"
echo "=========================================="
echo "API URL: $API_URL"
echo ""

# Track results
PASSED=0
FAILED=0

# Function to check endpoint
check_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local expected_status="$4"
    local data="$5"

    if [ "$method" = "GET" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL$endpoint")
    else
        response=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" -H "Content-Type: application/json" -d "$data" "$API_URL$endpoint")
    fi

    if [ "$response" = "$expected_status" ]; then
        echo "✅ $name"
        ((PASSED++))
        return 0
    else
        echo "❌ $name (expected $expected_status, got $response)"
        ((FAILED++))
        return 1
    fi
}

# 1. Health Endpoints
echo "=== Health Endpoints ==="
check_endpoint "GET /health" "GET" "/health" "200"
check_endpoint "GET /live" "GET" "/live" "200"
check_endpoint "GET /startup" "GET" "/startup" "200"
check_endpoint "GET /metrics" "GET" "/metrics" "200"
echo ""

# 2. Authentication
echo "=== Authentication ==="

# Register admin user (first user becomes admin)
echo "Registering admin user..."
curl -s -X POST "$API_URL/auth/register" \\
  -H "Content-Type: application/json" \\
  -d "{\\"email\\":\\"$ADMIN_EMAIL\\",\\"password\\":\\"$ADMIN_PASSWORD\\",\\"name\\":\\"Admin\\"}" > /dev/null 2>&1 || true

# Login
echo "Logging in as admin..."
LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/auth/login" \\
  -H "Content-Type: application/json" \\
  -d "{\\"email\\":\\"$ADMIN_EMAIL\\",\\"password\\":\\"$ADMIN_PASSWORD\\"}")

if echo "$LOGIN_RESPONSE" | grep -q "access_token"; then
    echo "✅ POST /auth/login"
    ((PASSED++))
    ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
    REFRESH_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"refresh_token":"[^"]*"' | cut -d'"' -f4)
else
    echo "❌ POST /auth/login"
    ((FAILED++))
    ACCESS_TOKEN=""
fi
echo ""

# 3. Protected Endpoints
if [ -n "$ACCESS_TOKEN" ]; then
    echo "=== Protected Endpoints ==="
    response=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $ACCESS_TOKEN" "$API_URL/auth/me")
    if [ "$response" = "200" ]; then
        echo "✅ GET /auth/me (with valid token)"
        ((PASSED++))
    else
        echo "❌ GET /auth/me (with valid token) - got $response"
        ((FAILED++))
    fi

    # Test without token
    response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/auth/me")
    if [ "$response" = "401" ] || [ "$response" = "403" ]; then
        echo "✅ GET /auth/me (without token) - correctly rejected"
        ((PASSED++))
    else
        echo "❌ GET /auth/me (without token) - should be rejected, got $response"
        ((FAILED++))
    fi
    echo ""
fi

# 4. API Key Management
if [ -n "$ACCESS_TOKEN" ]; then
    echo "=== API Key Management ==="
    response=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer $ACCESS_TOKEN" "$API_URL/auth/api-keys?name=TestKey")
    if [ "$response" = "200" ]; then
        echo "✅ POST /auth/api-keys"
        ((PASSED++))
    else
        echo "❌ POST /auth/api-keys - got $response"
        ((FAILED++))
    fi
    echo ""
fi

# 5. User Management (Admin)
if [ -n "$ACCESS_TOKEN" ]; then
    echo "=== User Management (Admin) ==="
    response=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $ACCESS_TOKEN" "$API_URL/users/")
    if [ "$response" = "200" ]; then
        echo "✅ GET /users/ (admin)"
        ((PASSED++))
    else
        echo "❌ GET /users/ (admin) - got $response"
        ((FAILED++))
    fi
    echo ""
fi

# 6. Security Headers
echo "=== Security Headers ==="
headers=$(curl -s -I "$API_URL/health")

if echo "$headers" | grep -qi "X-Content-Type-Options"; then
    echo "✅ X-Content-Type-Options header present"
    ((PASSED++))
else
    echo "❌ X-Content-Type-Options header missing"
    ((FAILED++))
fi

if echo "$headers" | grep -qi "X-Frame-Options"; then
    echo "✅ X-Frame-Options header present"
    ((PASSED++))
else
    echo "❌ X-Frame-Options header missing"
    ((FAILED++))
fi
echo ""

# Summary
echo "=========================================="
echo "Summary"
echo "=========================================="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✅ All quick tests passed! Staging environment looks good."
    exit 0
else
    echo "❌ Some tests failed. Check the issues above."
    exit 1
fi
