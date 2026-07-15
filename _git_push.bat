@echo off
rem ============================================================
rem ACAS v2 - GitHub Push Instructions
rem Run this AFTER creating the GitHub repository
rem ============================================================
echo.
echo === Step 1: Create GitHub Repository ===
echo.
echo 1. Open: https://github.com/new
echo 2. Repository name: acas-api
echo 3. Description: Africa Commodity Analytics System - Enterprise API v2
echo 4. Private (recommended for production)
echo 5. DO NOT initialize with README/.gitignore
echo 6. Click "Create repository"
echo.
echo === Step 2: Add remote and push ===
echo.
echo Copy the two commands from GitHub (under "...or push an existing repository")
echo It will look like:
echo   git remote add origin https://github.com/YOUR_USERNAME/acas-api.git
echo   git push -u origin main
echo.
echo Or run these (replace YOUR_USERNAME):
echo   git remote add origin https://github.com/YOUR_USERNAME/acas-api.git
echo   git push -u origin main
echo.
echo === Step 3: Configure GitHub Secrets (for CI/CD) ===
echo.
echo 1. Go to: https://github.com/YOUR_USERNAME/acas-api/settings/secrets/actions
echo 2. Add these secrets:
echo.
echo   ACAS_SECRET_KEY_STAGING
echo     Value: Run: python -c "import secrets; print(secrets.token_hex(32))"
echo.
echo   ACAS_DB_PASSWORD_STAGING
echo     Value: Run: python -c "import secrets; print(secrets.token_urlsafe(20))"
echo.
echo   STAGING_HOST       e.g. 203.0.113.42
echo   STAGING_USER       e.g. ubuntu
echo   SSH_KEY            (private key with staging server access)
echo   DOMAIN             e.g. yourdomain.com
echo.
echo === Step 4: Verify CI pipeline ===
echo.
echo After push, go to: https://github.com/YOUR_USERNAME/acas-api/actions
echo The CI workflow should run automatically (test + Docker build).
echo The Deploy workflow runs on merge to main.
echo.
pause
