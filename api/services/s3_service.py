"""
Document storage service.
Uses local filesystem when AWS creds aren't configured, S3 otherwise.
"""
import os
import logging
import shutil
from pathlib import Path
from config import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET

logger = logging.getLogger(__name__)

# Local storage directory (used when no S3 creds)
LOCAL_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage")


class S3Service:
    def __init__(self):
        self.bucket = S3_BUCKET
        self.use_local = not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY

        if self.use_local:
            os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)
            logger.info(f"S3Service using LOCAL storage: {LOCAL_STORAGE_DIR}")
            self.client = None
        else:
            import boto3
            self.client = boto3.client(
                "s3",
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            )
            logger.info(f"S3Service initialized: bucket={self.bucket}, region={AWS_REGION}")

    def upload_file(self, content: bytes, key: str, content_type: str = None) -> str:
        if self.use_local:
            filepath = os.path.join(LOCAL_STORAGE_DIR, key)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(content)
            return f"local://{key}"
        else:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type
            self.client.put_object(Bucket=self.bucket, Key=key, Body=content, **extra_args)
            return f"s3://{self.bucket}/{key}"

    def register_local_file(self, local_path: str, key: str) -> str:
        """Register an existing local file without copying it. Stores the real path."""
        # Store a symlink/reference file that points to the original
        ref_path = os.path.join(LOCAL_STORAGE_DIR, key + ".ref")
        os.makedirs(os.path.dirname(ref_path), exist_ok=True)
        with open(ref_path, "w") as f:
            f.write(local_path)
        return f"local://{key}"

    def download_file(self, key: str) -> bytes:
        if self.use_local:
            # Check for reference file first
            ref_path = os.path.join(LOCAL_STORAGE_DIR, key + ".ref")
            if os.path.exists(ref_path):
                with open(ref_path, "r") as f:
                    real_path = f.read().strip()
                with open(real_path, "rb") as f:
                    return f.read()
            filepath = os.path.join(LOCAL_STORAGE_DIR, key)
            with open(filepath, "rb") as f:
                return f.read()
        else:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        if self.use_local:
            # Return a local API endpoint for serving the file
            return f"/api/documents/serve/{key}"
        else:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )

    def delete_file(self, key: str):
        if self.use_local:
            for path in [
                os.path.join(LOCAL_STORAGE_DIR, key),
                os.path.join(LOCAL_STORAGE_DIR, key + ".ref"),
            ]:
                if os.path.exists(path):
                    os.remove(path)
        else:
            self.client.delete_object(Bucket=self.bucket, Key=key)

    def list_files(self, prefix: str) -> list:
        if self.use_local:
            base = os.path.join(LOCAL_STORAGE_DIR, prefix)
            if not os.path.exists(base):
                return []
            files = []
            for root, _, fnames in os.walk(base):
                for fname in fnames:
                    if fname.endswith(".ref"):
                        continue
                    rel = os.path.relpath(os.path.join(root, fname), LOCAL_STORAGE_DIR)
                    files.append(rel.replace("\\", "/"))
            return files
        else:
            response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            return [obj["Key"] for obj in response.get("Contents", [])]
