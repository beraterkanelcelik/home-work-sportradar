#!/usr/bin/env python3
"""
Script to initialize MinIO bucket for Langfuse
"""

import subprocess
import sys
import time


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
    try:
        # Try to create bucket using curl (simplified, may not work with auth)
        result = subprocess.run(
            [
                "curl",
                "-X",
                "PUT",
                "http://minio:9000/langfuse-events",
                "-H",
                "Authorization: AWS4-HMAC-SHA256 Credential=minio/minio",
            ],
            capture_output=True,
            timeout=10,
        )

        if result.returncode == 0:
            print("Created langfuse-events bucket")
        elif (
            b"BucketAlreadyExists" in result.stderr
            or b"BucketAlreadyOwnedByYou" in result.stderr
        ):
            print("langfuse-events bucket already exists")
        else:
            print(f"Warning: Could not create bucket: {result.stderr.decode()}")
    except Exception as e:
        print(f"Warning: Could not create MinIO bucket: {e}")


if __name__ == "__main__":
    if wait_for_minio():
        create_bucket()
    else:
        print("MinIO not ready, skipping bucket creation")
        sys.exit(1)
