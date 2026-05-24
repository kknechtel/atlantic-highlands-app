#!/bin/bash
# Sync local Atlantic Highlands data to AWS
# Run from: cd atlantic-highlands && bash sync_to_aws.sh
#
# Credentials are sourced from AWS Secrets Manager (bank-processor-api-secrets)
# or, as a fallback, from the local environment. The previous version of this
# script hardcoded the RDS password in git — that credential MUST be rotated.

set -e

RDS_HOST="atlantic-highlands-db.c4xoyiqaey7u.us-east-1.rds.amazonaws.com"
RDS_USER="ahAdmin"
RDS_DB="atlantic_highlands"
S3_BUCKET="atlantic-highlands-documents-738265942536"
EC2_INSTANCE="i-06424a799368c7d6d"
SECRET_ID="${AH_RDS_SECRET_ID:-atlantic-highlands/production}"
SECRET_KEY="${AH_RDS_SECRET_KEY:-RDS_PASSWORD}"

if [ -z "${RDS_PASS:-}" ]; then
  RDS_PASS=$(aws secretsmanager get-secret-value \
    --secret-id "${SECRET_ID}" \
    --query 'SecretString' --output text 2>/dev/null \
    | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('${SECRET_KEY}',''))" \
    2>/dev/null || true)
fi
if [ -z "${RDS_PASS:-}" ]; then
  echo "ERROR: RDS password not available." >&2
  echo "  Set it as env (export RDS_PASS=...) or put it in AWS Secrets Manager" >&2
  echo "  at secret ${SECRET_ID} under key ${SECRET_KEY}." >&2
  exit 1
fi

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
