import os
from minio import Minio
from minio.error import S3Error

# Load environment variables
minio_endpoint = os.getenv("MINIO_ENDPOINT")
access_key = os.getenv("MINIO_ACCESS_KEY")
secret_key = os.getenv("MINIO_SECRET_KEY")
bucket_name = os.getenv("BUCKET_NAME")

# Check if all required environment variables are set
if not all([minio_endpoint, access_key, secret_key, bucket_name]):
    raise ValueError("One or more required environment variables are missing.")

# Initialize MinIO client
minio_client = Minio(
    minio_endpoint.replace("http://", "").replace("https://", ""),
    access_key=access_key,
    secret_key=secret_key,
    secure=minio_endpoint.startswith("https")
)

def list_objects_in_bucket(bucket_name, minio_client):
    try:
        # List objects in the specified bucket
        objects = minio_client.list_objects(bucket_name, recursive=True)
        print(f"Objects in bucket '{bucket_name}':")
        for obj in objects:
            print(f" - {obj.object_name}")
    except S3Error as e:
        print(f"Error listing objects in bucket '{bucket_name}': {e}")

# Run the function to list the objects in the specified bucket
list_objects_in_bucket(bucket_name, minio_client)
