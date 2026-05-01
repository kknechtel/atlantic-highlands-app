#!/bin/bash
# Sync local Atlantic Highlands data to AWS
# Run from: cd atlantic-highlands && bash sync_to_aws.sh

set -e

RDS_HOST="atlantic-highlands-db.c4xoyiqaey7u.us-east-1.rds.amazonaws.com"
RDS_USER="ahAdmin"
RDS_PASS="AH-Docs-2026!"
RDS_DB="atlantic_highlands"
S3_BUCKET="atlantic-highlands-documents-738265942536"
EC2_INSTANCE="i-06424a799368c7d6d"

echo "=== Atlantic Highlands AWS Sync ==="

# 1. Sync documents to S3
echo "[1/4] Syncing documents to S3..."
aws s3 sync api/storage/ "s3://${S3_BUCKET}/" --exclude "*.ref" --exclude "__pycache__/*" --exclude "*.pyc"
echo "  Done."

# 2. Dump local database
echo "[2/4] Dumping local database..."
pg_dump -h localhost -U postgres -d atlantic_highlands --no-owner --no-privileges -F c -f /tmp/ah_sync.backup
echo "  Done: $(du -sh /tmp/ah_sync.backup | cut -f1)"

# 3. Restore to RDS (drop and recreate)
echo "[3/4] Syncing database to RDS..."
PGPASSWORD="${RDS_PASS}" pg_restore -h "${RDS_HOST}" -U "${RDS_USER}" -d "${RDS_DB}" --clean --no-owner --no-privileges /tmp/ah_sync.backup 2>&1 | tail -3
echo "  Done."

# 4. Restart EC2 API
echo "[4/4] Restarting production API..."
aws ssm send-command \
  --instance-ids "${EC2_INSTANCE}" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /opt/atlantic-highlands && git pull && systemctl restart ah-api"]' \
  --query 'Command.CommandId' --output text
echo "  Done."

echo ""
echo "=== Sync complete! ==="
echo "  Frontend: https://ahnj.info"
echo "  Backend:  http://35.173.239.249"
