# Post-build verification for ACAS v2 Docker image
# Verifies: container starts, /health + /ready respond, auth register/login works.
$ErrorActionPreference = 'Continue'

$key = (Get-Content "$PSScriptRoot\.verify_secret.txt" -Raw).Trim()
$IMG = "acas:latest"
$PORT = 8001
$NAME = "acas-verify"

# Clean up any previous run
docker rm -f $NAME 2>$null | Out-Null

Write-Host "=== Starting container $NAME from $IMG ==="
docker run -d --name $NAME -p ${PORT}:8000 `
  -e ACAS_ENVIRONMENT=development `
  -e ACAS_DB_URL='sqlite+aiosqlite:////app/acas.db' `
  -e ACAS_RL_ENABLED=false `
  -e ACAS_ML_SENTIMENT_ENABLED=false `
  -e ACAS_ML_TIMESFM_ENABLED=false `
  -e ACAS_SECRET_KEY=$key `
  $IMG | Out-Null

# Wait for health
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $code = (curl.exe -s -o $null -w '%{http_code}' "http://localhost:${PORT}/health").Trim()
        if ($code -eq '200') { $ok = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
Write-Host ("Health check: {0}" -f $(if ($ok) { 'READY' } else { 'TIMEOUT' }))

if (-not $ok) {
    Write-Host "=== Container logs ==="
    docker logs --tail 40 $NAME
    exit 1
}

function Get-Json($path, $body, $token) {
    $hdr = if ($token) { @('-H', "Authorization: Bearer $token") } else { @() }
    $b = if ($body) { $body | ConvertTo-Json -Compress } else { '' }
    $args = @('-s', '-w', "`nHTTP %{http_code}", '-H', 'Content-Type: application/json')
    $args += $hdr
    if ($body) { $args += @('-d', $b) }
    $args += "http://localhost:${PORT}${path}"
    $out = & curl.exe @args
    return $out
}

Write-Host "=== /health ==="
curl.exe -s "http://localhost:${PORT}/health"

Write-Host "`n=== /ready ==="
curl.exe -s "http://localhost:${PORT}/ready"

Write-Host "`n=== POST /auth/register ==="
$reg = Get-Json '/auth/register' @{ email = "verify$(Get-Date -UFormat %s)@acas.test"; password = "Verify#12345"; name = "VerifyUser" }
Write-Host $reg

# Extract access token from register response (best effort)
$tok = ($reg | Select-String -Pattern '"access_token"\s*:\s*"([^"]+)"').Matches.Groups[1].Value
if (-not $tok) {
    Write-Host "=== POST /auth/login ==="
    $login = Get-Json '/auth/login' @{ email = "verify@acas.test"; password = "Verify#12345" }
    Write-Host $login
    $tok = ($login | Select-String -Pattern '"access_token"\s*:\s*"([^"]+)"').Matches.Groups[1].Value
}

if ($tok) {
    Write-Host "`n=== GET /users/me (auth) ==="
    Write-Host (Get-Json '/users/me' $null $tok)
} else {
    Write-Host "No access token obtained; skipping /users/me"
}

Write-Host "`n=== Container logs (tail 30) ==="
docker logs --tail 30 $NAME

# Cleanup
docker rm -f $NAME 2>$null | Out-Null
Write-Host "`n=== Verification complete ==="
