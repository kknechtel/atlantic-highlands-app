"""
Set up AWS Secrets Manager for Atlantic Highlands production.
Run once to create the secret, then store all sensitive config there.

Usage:
    python setup_secrets.py
"""
import json
import secrets
import boto3

SECRET_NAME = "atlantic-highlands/production"
REGION = "us-east-1"

# Generate a strong JWT secret
jwt_secret = secrets.token_urlsafe(48)

secret_values = {
    "DATABASE_URL": "postgresql://ahAdmin:AH-Docs-2026!@atlantic-highlands-db.c4xoyiqaey7u.us-east-1.rds.amazonaws.com:5432/atlantic_highlands",
    "SECRET_KEY": secrets.token_urlsafe(48),
    "JWT_SECRET": jwt_secret,
    "JWT_EXPIRATION_HOURS": "24",
    "ALLOWED_ORIGINS": "https://ahnj.info,https://www.ahnj.info,https://atlantic-highlands.amplifyapp.com,http://localhost:3000",
    "S3_BUCKET": "atlantic-highlands-documents-738265942536",
    "AWS_REGION": REGION,
    "ANTHROPIC_API_KEY": "",  # Fill in
    "GEMINI_API_KEY": "",     # Fill in
    "DEBUG": "false",
}

client = boto3.client("secretsmanager", region_name=REGION)

try:
    # Try to update existing secret
    client.put_secret_value(
        SecretId=SECRET_NAME,
        SecretString=json.dumps(secret_values),
    )
    print(f"Updated secret: {SECRET_NAME}")
except client.exceptions.ResourceNotFoundException:
    # Create new secret
    client.create_secret(
        Name=SECRET_NAME,
        Description="Atlantic Highlands production configuration",
        SecretString=json.dumps(secret_values),
    )
    print(f"Created secret: {SECRET_NAME}")

print(f"\nSecret stored in AWS Secrets Manager: {SECRET_NAME}")
print(f"JWT Secret: {jwt_secret[:8]}...{jwt_secret[-8:]}")
print(f"\nTo use in production, set this env var on your EC2 instance:")
print(f"  AWS_SECRETS_NAME={SECRET_NAME}")
print(f"\nThen the app will load all config from Secrets Manager automatically.")
print(f"\nDon't forget to fill in ANTHROPIC_API_KEY and GEMINI_API_KEY!")
