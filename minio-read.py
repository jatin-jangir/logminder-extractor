from minio import Minio
from minio.error import S3Error
import os

# Load environment variables
minio_endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")  # Only the host and port
access_key = os.getenv("MINIO_ACCESS_KEY")
secret_key = os.getenv("MINIO_SECRET_KEY")
bucket_name = os.getenv("BUCKET_NAME")

# Check for missing environment variables
if not all([minio_endpoint, access_key, secret_key, bucket_name]):
    raise ValueError("One or more required environment variables are missing.")

# Initialize MinIO client
minio_client = Minio(
    minio_endpoint.replace("http://", "").replace("https://", ""),
    access_key=access_key,
    secret_key=secret_key,
    secure=minio_endpoint.startswith("https")
)

def get_file_content(bucket_name, object_name, minio_client):
    try:
        # Retrieve the object from the bucket
        response = minio_client.get_object(bucket_name, object_name)
        
        # Read and print the content of the object
        file_content = response.read().decode('utf-8')
        print(f"Content of '{object_name}':\n{file_content}")
        
        # Close the response object
        response.close()
        response.release_conn()
    except S3Error as e:
        print(f"Error retrieving object '{object_name}' from bucket '{bucket_name}': {e}")

# Specify the object (file) name
object_name = "test-ns/time-printer-697bbd8549-7xvsw/time-printer/previous/06-09-2024/13-58-59.log"

# Fetch and print the content of the specified object
get_file_content(bucket_name, object_name, minio_client)
