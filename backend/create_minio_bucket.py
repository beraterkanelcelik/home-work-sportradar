#!/usr/bin/env python3
"""
Script to initialize MinIO bucket for Langfuse
"""

import os
import subprocess
import sys
import time

from minio import Minio
from minio.error import S3Error


def wait_for_minio():
    """Wait for MinIO to be ready"""
    print("Waiting for MinIO...")
    for _ in range(30):  # Wait up to 60 seconds
        try:
            result = subprocess.run(
                ["curl", "-f", "http://minio:9000/minio/health/ready"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except:
            pass
        time.sleep(2)
    return False


def create_bucket():
    """Create langfuse-events bucket if it doesn't exist"""
    bucket_name = os.getenv("MINIO_BUCKET", "langfuse-events")
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
    access_key = os.getenv("MINIO_ROOT_USER", "minio")
    secret_key = os.getenv("MINIO_ROOT_PASSWORD", "minio123")

    try:
        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=False,
        )

        if client.bucket_exists(bucket_name):
            print(f"{bucket_name} bucket already exists")
            return

        client.make_bucket(bucket_name)
        print(f"Created {bucket_name} bucket")
    except S3Error as exc:
        if exc.code in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
            print(f"{bucket_name} bucket already exists")
        else:
            print(f"Warning: Could not create bucket: {exc}")
    except Exception as exc:
        print(f"Warning: Could not create MinIO bucket: {exc}")


if __name__ == "__main__":
    if wait_for_minio():
        create_bucket()
    else:
        print("MinIO not ready, skipping bucket creation")
        sys.exit(1)
