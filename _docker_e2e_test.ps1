param([string]$baseUrl = "http://localhost:8000", [int]$iterations = 1)

function Get-Code($url, $headers = @{}) {
    try {
        $resp = Invoke-WebRequest -Uri $url -Headers $headers -Method GET -TimeoutSec 5 -UseBasicParsing
        return [int]$resp.StatusCode
    } catch {
        return [int]$_.Exception.Response.StatusCode
    }
}

$ok = $true

# Health
$code = Get-Code "$baseUrl/health"
Write-Output "GET /health -> $code"
if ($code -ne 200) { $ok = $false }

# Register
$body = @{email="e2e@test.com";password="Test1234!";name="E2E Test User"} | ConvertTo-Json
try {
    $r = Invoke-RestMethod -Uri "$baseUrl/auth/register" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 10 -UseBasicParsing
    $token = $r.access_token
    Write-Output "POST /auth/register -> created user $($r.user.id)"
} catch {
    Write-Output "POST /auth/register -> FAIL: $_"
    $ok = $false
    $token = $null
}

if ($token) {
    $auth = @{Authorization="Bearer $token"}
    # Me
    $code = Get-Code "$baseUrl/users/me" $auth
    Write-Output "GET /users/me -> $code"
    if ($code -ne 200) { $ok = $false }

    # Forecast
    $fbody = @{category="energy";region="global";forecast_days=7} | ConvertTo-Json
    try {
        $f = Invoke-RestMethod -Uri "$baseUrl/forecast" -Method POST -Body $fbody -ContentType "application/json" -Headers $auth -TimeoutSec 30 -UseBasicParsing
        Write-Output "POST /forecast -> $($f.status)"
    } catch {
        Write-Output "POST /forecast -> FAIL: $_"
        $ok = $false
    }
}

if ($ok) { Write-Output "ALL CHECKS PASSED" }
exit [int](-not $ok)
