#!/bin/bash
# ACAS v2 - Disaster Recovery Script
# Industrial deployment requirement: Test database failover and recovery

set -e

echo "=========================================="
echo "ACAS v2 Disaster Recovery Test"
echo "=========================================="

# Configuration
DB_NAME="acas"
DB_USER="acas"
DB_PASSWORD="acas_prod_2024"
DB_HOST="localhost"
DB_PORT="5432"
BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Create backup
echo -e "${YELLOW}[Step 1/6] Creating database backup...${NC}"
mkdir -p "$BACKUP_DIR"
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" > "$BACKUP_DIR/backup_$TIMESTAMP.sql"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Backup created: $BACKUP_DIR/backup_$TIMESTAMP.sql${NC}"
else
    echo -e "${RED}✗ Backup failed${NC}"
    exit 1
fi

# Step 2: Simulate database failure
echo -e "${YELLOW}[Step 2/6] Simulating database failure...${NC}"
echo "Stopping PostgreSQL service..."
# Windows: net stop postgresql-x64-17
# Linux: systemctl stop postgresql
if [ "$OSTYPE" == "linux-gnu"* ]; then
    sudo systemctl stop postgresql
elif [[ "$OSTYPE" == "msys"* ]] || [[ "$OSTYPE" == "cygwin"* ]]; then
    net stop postgresql-x64-17 || true
fi

echo -e "${YELLOW}Database stopped. Waiting 10 seconds...${NC}"
sleep 10

# Step 3: Verify application handles DB failure gracefully
echo -e "${YELLOW}[Step 3/6] Verifying application handles DB failure...${NC}"
# Run health check (should return 503 for /ready)
curl -s http://localhost:8000/ready | grep -q "ready.*false" && echo -e "${GREEN}✓ Application correctly reports not ready${NC}" || echo -e "${RED}✗ Application did not handle DB failure gracefully${NC}"

# Step 4: Restore database
echo -e "${YELLOW}[Step 4/6] Restoring database...${NC}"
echo "Starting PostgreSQL service..."
if [ "$OSTYPE" == "linux-gnu"* ]; then
    sudo systemctl start postgresql
elif [[ "$OSTYPE" == "msys"* ]] || [[ "$OSTYPE" == "cygwin"* ]]; then
    net start postgresql-x64-17 || true
fi

echo "Waiting for PostgreSQL to be ready..."
sleep 5

# Drop and recreate database
echo "Dropping and recreating database..."
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c "DROP DATABASE IF EXISTS ${DB_NAME}_restore;"
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c "CREATE DATABASE ${DB_NAME}_restore;"

# Restore backup
echo "Restoring backup..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "${DB_NAME}_restore" < "$BACKUP_DIR/backup_$TIMESTAMP.sql"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Database restored successfully${NC}"
else
    echo -e "${RED}✗ Database restore failed${NC}"
    exit 1
fi

# Step 5: Verify restore
echo -e "${YELLOW}[Step 5/6] Verifying restored database...${NC}"
TABLE_COUNT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "${DB_NAME}_restore" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
echo "Tables in restored database: $TABLE_COUNT"

# Step 6: Switch application to restored database
echo -e "${YELLOW}[Step 6/6] Switching application to restored database...${NC}"
echo "Updating .env file..."
sed -i "s/ACAS_DB_URL=.*/ACAS_DB_URL=postgresql+psycopg:\/\/$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT\/${DB_NAME}_restore/" .env

echo -e "${GREEN}✓ Disaster recovery test completed successfully${NC}"
echo ""
echo "Summary:"
echo "  - Backup created: $BACKUP_DIR/backup_$TIMESTAMP.sql"
echo "  - Database restored to: ${DB_NAME}_restore"
echo "  - Application config updated to use restored database"
echo ""
echo "Next steps:"
echo "  1. Verify application works with restored database"
echo "  2. Run: curl http://localhost:8000/ready"
echo "  3. If OK, switch production to restored database"
echo "  4. Clean up: drop ${DB_NAME}_restore after verification"

exit 0
