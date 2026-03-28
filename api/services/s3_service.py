"""AWS S3 service for document storage."""
import logging
import boto3
from botocore.exceptions import ClientError
from config import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET

logger = logging.getLogger(__name__)


class S3Service:
    def __init__(self):
        self.bucket = S3_BUCKET
        self.client = boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )
        logger.info(f"S3Service initialized: bucket={self.bucket}, region={AWS_REGION}")

    def upload_file(self, content: bytes, key: str, content_type: str = None) -> str:
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, **extra_args)
        return f"s3://{self.bucket}/{key}"

    def download_file(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def delete_file(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def list_files(self, prefix: str) -> list:
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return [obj["Key"] for obj in response.get("Contents", [])]
