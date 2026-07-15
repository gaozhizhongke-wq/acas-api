"""
ACAS v2 - API Documentation Generator
Industrial deployment requirement: Complete API documentation
"""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
import json

# Import the app
from api.main import app

def generate_openapi_schema():
    """Generate OpenAPI schema"""
    return get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )

def generate_api_docs():
    """Generate comprehensive API documentation"""

    # Generate OpenAPI schema
    openapi_schema = generate_openapi_schema()

    # Save as JSON
    with open("docs/openapi.json", "w") as f:
        json.dump(openapi_schema, f, indent=2)

    print("✓ OpenAPI schema saved to docs/openapi.json")

    # Generate markdown documentation
    markdown_docs = """# ACAS v2 API Documentation

## Overview
ACAS v2 (AI-Powered Customer Analysis System) provides RESTful APIs for sentiment analysis, brand insights, and customer feedback processing.

Base URL: `http://localhost:8000`

## Authentication
All API endpoints (except `/health`, `/ready`, `/auth/register`, `/auth/login`) require authentication via JWT Bearer token.

### Obtaining a Token
```bash
# Register
POST /api/auth/register
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "name": "John Doe"
}

# Login
POST /api/auth/login
{
  "username": "user@example.com",
  "password": "SecurePass123!"
}

# Response
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### Using the Token
Include the token in the `Authorization` header:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Endpoints

### Health Check

#### `GET /health`
Basic health check (always returns 200 if process is alive)

**Response:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2026-07-02T00:00:00Z"
}
```

#### `GET /ready`
Readiness probe (checks database and Redis connectivity)

**Response (200 if ready):**
```json
{
  "ready": true,
  "checks": {
    "database": true,
    "redis": true
  },
  "timestamp": "2026-07-02T00:00:00Z"
}
```

**Response (503 if not ready):**
```json
{
  "ready": false,
  "checks": {
    "database": true,
    "redis": false
  },
  "timestamp": "2026-07-02T00:00:00Z"
}
```

### Authentication

#### `POST /api/auth/register`
Register a new user

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "name": "John Doe"
}
```

**Response (201):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "name": "John Doe",
  "created_at": "2026-07-02T00:00:00Z"
}
```

#### `POST /api/auth/login`
Login with email and password

**Request Body:**
```json
{
  "username": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

#### `POST /api/auth/refresh`
Refresh access token using refresh token

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

#### `POST /api/auth/logout`
Logout (invalidate refresh token)

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "message": "Logged out successfully"
}
```

#### `POST /api/auth/api-keys`
Create API key for programmatic access

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "name": "My API Key"
}
```

**Response (201):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "key": "ak_1234567890abcdef",
  "name": "My API Key",
  "created_at": "2026-07-02T00:00:00Z"
}
```

### User Management

#### `GET /api/users/me`
Get current user profile

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "name": "John Doe",
  "created_at": "2026-07-02T00:00:00Z"
}
```

#### `PATCH /api/users/me`
Update current user profile

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "name": "John Smith"
}
```

**Response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "name": "John Smith",
  "created_at": "2026-07-02T00:00:00Z"
}
```

### Sentiment Analysis

#### `POST /api/sentiment/analyze`
Analyze sentiment of text

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "text": "This product is amazing!"
}
```

**Response (200):**
```json
{
  "sentiment": "positive",
  "score": 0.95,
  "confidence": 0.92,
  "aspects": {
    "quality": "positive",
    "price": "neutral"
  }
}
```

### Brand Insights

#### `GET /api/insights`
Get brand insights

**Headers:**
```
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `brand` (required): Brand name
- `limit` (optional): Number of insights to return (default: 10)
- `start_date` (optional): Start date (ISO format)
- `end_date` (optional): End date (ISO format)

**Response (200):**
```json
{
  "brand": "ExampleBrand",
  "insights": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "text": "Great product, highly recommend!",
      "sentiment": "positive",
      "score": 0.95,
      "source": "twitter",
      "created_at": "2026-07-02T00:00:00Z"
    }
  ],
  "summary": {
    "total": 100,
    "positive": 65,
    "negative": 20,
    "neutral": 15
  }
}
```

## Rate Limiting

API requests are rate-limited per IP address:

- General endpoints: 100 requests/minute
- Login endpoint: 5 requests/minute (to prevent brute force)
- Registration endpoint: 3 requests/minute

If rate limit is exceeded, the API returns HTTP 429 (Too Many Requests).

**Response Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1625097600
```

## Error Handling

All errors return JSON with the following format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input",
    "details": {
      "field": "email",
      "issue": "Invalid email format"
    }
  }
}
```

### Common Error Codes

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | VALIDATION_ERROR | Invalid request body |
| 401 | UNAUTHORIZED | Invalid or missing token |
| 403 | FORBIDDEN | Insufficient permissions |
| 404 | NOT_FOUND | Resource not found |
| 429 | RATE_LIMITED | Rate limit exceeded |
| 500 | INTERNAL_ERROR | Internal server error |

## Pagination

List endpoints support pagination via `limit` and `offset` parameters:

```
GET /api/insights?brand=Example&limit=10&offset=20
```

**Response:**
```json
{
  "data": [...],
  "pagination": {
    "total": 100,
    "limit": 10,
    "offset": 20,
    "has_more": true
  }
}
```

## Webhooks

ACAS v2 supports webhooks for real-time notifications. Configure webhooks in the dashboard.

**Webhook Events:**
- `sentiment.analyzed` - Sent when sentiment analysis completes
- `insight.created` - Sent when new insight is created
- `user.registered` - Sent when new user registers

**Webhook Payload:**
```json
{
  "event": "sentiment.analyzed",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "sentiment": "positive",
    "score": 0.95
  },
  "timestamp": "2026-07-02T00:00:00Z"
}
```

## SDKs and Examples

### Python
```python
import requests

# Login
response = requests.post("http://localhost:8000/api/auth/login", data={
    "username": "user@example.com",
    "password": "SecurePass123!"
})
token = response.json()["access_token"]

# Analyze sentiment
headers = {"Authorization": f"Bearer {token}"}
response = requests.post("http://localhost:8000/api/sentiment/analyze",
    json={"text": "This product is amazing!"},
    headers=headers
)
print(response.json())
```

### JavaScript
```javascript
// Login
const response = await fetch('http://localhost:8000/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: 'username=user@example.com&password=SecurePass123!'
});
const { access_token } = await response.json();

// Analyze sentiment
const sentimentResponse = await fetch('http://localhost:8000/api/sentiment/analyze', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access_token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ text: 'This product is amazing!' })
});
console.log(await sentimentResponse.json());
```

## Support

For support, contact:
- Email: support@acas.com
- Documentation: https://docs.acas.com
- GitHub Issues: https://github.com/acas/acas-v2/issues

"""

    # Save markdown documentation
    with open("docs/API.md", "w") as f:
        f.write(markdown_docs)

    print("✓ API documentation saved to docs/API.md")

    return openapi_schema, markdown_docs


if __name__ == "__main__":
    print("Generating API documentation...")
    generate_api_docs()
    print("Done!")
