# ACAS v2 - Staging Environment Quick Test (PowerShell)
# Run this to quickly validate staging deployment

$API_URL = "http://localhost:8000"
$AdminEmail = "admin@acas-staging.com"
$AdminPassword = "AdminPassword123!"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "ACAS v2 - Staging Environment Test" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "API URL: $API_URL"
Write-Host ""

$passed = 0
$failed = 0

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Method,
        [string]$Endpoint,
        [int]$ExpectedStatus,
        [string]$Body = ""
    )
    
    try {
        $headers = @{}
        if ($Method -eq "POST" -or $Method -eq "PUT" -or $Method -eq "DELETE") {
            $headers["Content-Type"] = "application/json"
        }
        
        if ($Body -ne "") {
            $response = Invoke-RestMethod -Uri "$API_URL$Endpoint" -Method $Method -Headers $headers -Body $Body -ErrorAction Stop
            $statusCode = 200  # If no error, assume 200
        } else {
            $response = Invoke-RestMethod -Uri "$API_URL$Endpoint" -Method $Method -Headers $headers -ErrorAction Stop
            $statusCode = 200
        }
        
        if ($ExpectedStatus -eq $statusCode) {
            Write-Host "✅ $Name" -ForegroundColor Green
            return @{
                Success = $true
                Response = $response
            }
        } else {
            Write-Host "❌ $Name (expected $ExpectedStatus, got $statusCode)" -ForegroundColor Red
            return @{
                Success = $false
                Response = $null
            }
        }
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq $ExpectedStatus) {
            Write-Host "✅ $Name" -ForegroundColor Green
            return @{
                Success = $true
                Response = $null
            }
        } else {
            Write-Host "❌ $Name (expected $ExpectedStatus, got $statusCode)" -ForegroundColor Red
            return @{
                Success = $false
                Response = $null
            }
        }
    }
}

# 1. Health Endpoints
Write-Host "=== Health Endpoints ===" -ForegroundColor Yellow
$result = Test-Endpoint -Name "GET /health" -Method GET -Endpoint "/health" -ExpectedStatus 200
if ($result.Success) { $passed++ } else { $failed++ }

$result = Test-Endpoint -Name "GET /live" -Method GET -Endpoint "/live" -ExpectedStatus 200
if ($result.Success) { $passed++ } else { $failed++ }

$result = Test-Endpoint -Name "GET /startup" -Method GET -Endpoint "/startup" -ExpectedStatus 200
if ($result.Success) { $passed++ } else { $failed++ }

$result = Test-Endpoint -Name "GET /metrics" -Method GET -Endpoint "/metrics" -ExpectedStatus 200
if ($result.Success) { $passed++ } else { $failed++ }

Write-Host ""

# 2. Authentication
Write-Host "=== Authentication ===" -ForegroundColor Yellow

# Register admin (first user becomes admin)
Write-Host "Registering admin user..." -ForegroundColor Gray
$registerBody = @{
    email = $AdminEmail
    password = $AdminPassword
    name = "Admin User"
} | ConvertTo-Json

try {
    $registerResponse = Invoke-RestMethod -Uri "$API_URL/auth/register" -Method POST -Body $registerBody -ContentType "application/json" -ErrorAction SilentlyContinue
} catch {
    # User might already exist
}

# Login
Write-Host "Logging in as admin..." -ForegroundColor Gray
$loginBody = @{
    email = $AdminEmail
    password = $AdminPassword
} | ConvertTo-Json

try {
    $loginResponse = Invoke-RestMethod -Uri "$API_URL/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
    $accessToken = $loginResponse.access_token
    $refreshToken = $loginResponse.refresh_token
    
    if ($accessToken -and $refreshToken) {
        Write-Host "✅ POST /auth/login" -ForegroundColor Green
        $passed++
    } else {
        Write-Host "❌ POST /auth/login (missing tokens)" -ForegroundColor Red
        $failed++
    }
} catch {
    Write-Host "❌ POST /auth/login" -ForegroundColor Red
    $failed++
}

Write-Host ""

# 3. Protected Endpoints
if ($accessToken) {
    Write-Host "=== Protected Endpoints ===" -ForegroundColor Yellow
    
    try {
        $headers = @{ Authorization = "Bearer $accessToken" }
        $meResponse = Invoke-RestMethod -Uri "$API_URL/auth/me" -Method GET -Headers $headers
        Write-Host "✅ GET /auth/me (with valid token)" -ForegroundColor Green
        $passed++
    } catch {
        Write-Host "❌ GET /auth/me (with valid token)" -ForegroundColor Red
        $failed++
    }
    
    # Test without token
    try {
        $meResponse = Invoke-RestMethod -Uri "$API_URL/auth/me" -Method GET -ErrorAction Stop
        Write-Host "❌ GET /auth/me (without token) - should be rejected" -ForegroundColor Red
        $failed++
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 401 -or $_.Exception.Response.StatusCode.value__ -eq 403) {
            Write-Host "✅ GET /auth/me (without token) - correctly rejected" -ForegroundColor Green
            $passed++
        } else {
            Write-Host "❌ GET /auth/me (without token) - wrong status" -ForegroundColor Red
            $failed++
        }
    }
    
    Write-Host ""
}

# 4. API Key Management
if ($accessToken) {
    Write-Host "=== API Key Management ===" -ForegroundColor Yellow
    
    try {
        $headers = @{ Authorization = "Bearer $accessToken" }
        $apiKeyResponse = Invoke-RestMethod -Uri "$API_URL/auth/api-keys?name=StagingTestKey" -Method POST -Headers $headers
        
        if ($apiKeyResponse.key -and $apiKeyResponse.id) {
            Write-Host "✅ POST /auth/api-keys" -ForegroundColor Green
            $passed++
        } else {
            Write-Host "❌ POST /auth/api-keys (missing key or id)" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host "❌ POST /auth/api-keys" -ForegroundColor Red
        $failed++
    }
    
    try {
        $headers = @{ Authorization = "Bearer $accessToken" }
        $apiKeysResponse = Invoke-RestMethod -Uri "$API_URL/auth/api-keys" -Method GET -Headers $headers
        
        if ($apiKeysResponse.keys) {
            Write-Host "✅ GET /auth/api-keys" -ForegroundColor Green
            $passed++
        } else {
            Write-Host "❌ GET /auth/api-keys (missing keys)" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host "❌ GET /auth/api-keys" -ForegroundColor Red
        $failed++
    }
    
    Write-Host ""
}

# 5. User Management (Admin)
if ($accessToken) {
    Write-Host "=== User Management (Admin) ===" -ForegroundColor Yellow
    
    try {
        $headers = @{ Authorization = "Bearer $accessToken" }
        $usersResponse = Invoke-RestMethod -Uri "$API_URL/users/" -Method GET -Headers $headers
        
        if ($usersResponse.total -ne $null) {
            Write-Host "✅ GET /users/ (admin)" -ForegroundColor Green
            $passed++
        } else {
            Write-Host "❌ GET /users/ (admin) (missing total)" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host "❌ GET /users/ (admin)" -ForegroundColor Red
        $failed++
    }
    
    Write-Host ""
}

# 6. Security Headers
Write-Host "=== Security Headers ===" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "$API_URL/health" -Method GET
    $headers = $response.Headers
    
    if ($headers.ContainsKey("X-Content-Type-Options")) {
        Write-Host "✅ X-Content-Type-Options header present" -ForegroundColor Green
        $passed++
    } else {
        Write-Host "❌ X-Content-Type-Options header missing" -ForegroundColor Red
        $failed++
    }
    
    if ($headers.ContainsKey("X-Frame-Options")) {
        Write-Host "✅ X-Frame-Options header present" -ForegroundColor Green
        $passed++
    } else {
        Write-Host "❌ X-Frame-Options header missing" -ForegroundColor Red
        $failed++
    }
} catch {
    Write-Host "❌ Security headers check failed" -ForegroundColor Red
    $failed++
}

Write-Host ""

# Summary
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Passed: $passed" -ForegroundColor Green
Write-Host "Failed: $failed" -ForegroundColor $(if ($failed -gt 0) { "Red" } else { "Green" })
Write-Host ""

if ($failed -eq 0) {
    Write-Host "✅ All tests passed! Staging environment looks good." -ForegroundColor Green
    exit 0
} else {
    Write-Host "❌ Some tests failed. Check the issues above." -ForegroundColor Red
    exit 1
}
