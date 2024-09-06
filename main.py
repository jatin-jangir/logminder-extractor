from kubernetes import client, config
from minio import Minio
from minio.error import S3Error
import os
import datetime
import io

def save_logs_to_minio(namespace, bucket_name, minio_client):
    # Load Kubernetes configuration
    config.load_kube_config(config_file=os.getenv("KUBECONFIG_FILE"))
    
    # Create Kubernetes API client
    v1 = client.CoreV1Api()

    # Get all pods in the specified namespace
    pods = v1.list_namespaced_pod(namespace)
    # Iterate through all the pods
    for pod in pods.items:
        pod_name = pod.metadata.name

        # Iterate through all containers in the pod
        for container in pod.spec.containers:
            container_name = container.name

            now = datetime.datetime.now()

            # Store the time in a string (in ISO 8601 format, for example)
            stored_time_str = "2024-09-04T20:25:17Z"  # Wed Sep 4 20:13:13 UTC 2024

            # Convert the string to a datetime object
            stored_time = datetime.datetime.strptime(stored_time_str, "%Y-%m-%dT%H:%M:%SZ")
            stored_time = stored_time.replace(tzinfo=datetime.timezone.utc)

            # Get the current time in UTC
            current_time = datetime.datetime.now(datetime.timezone.utc)

            # Calculate the time difference in seconds
            since_seconds = int((current_time - stored_time).total_seconds())

            # Get logs from the specified seconds ago
            log = v1.read_namespaced_pod_log(name=pod_name, namespace=namespace, container=container_name, since_seconds=since_seconds)

            # Print the logs
            print(log)

            # Get the current date and time
            date_str = now.strftime("%d-%m-%Y")
            time_str = now.strftime("%H-%M-%S")

            # Define the MinIO object name (path)
            object_name = f"{namespace}/{container_name}/{date_str}/{time_str}.log"

            # Wrap the log data in a BytesIO object
            log_data = io.BytesIO(log.encode('utf-8'))
            # Upload the log to MinIO
            try:
                minio_client.put_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    data=log_data,
                    length=len(log),
                    content_type="text/plain"
                )
                print(f"Uploaded logs for container '{container_name}' in pod '{pod_name}' to MinIO at {object_name}")
            except S3Error as e:
                print(f"Error uploading to MinIO: {e}")

# Load environment variables
minio_endpoint = os.getenv("MINIO_ENDPOINT")
access_key = os.getenv("MINIO_ACCESS_KEY")
secret_key = os.getenv("MINIO_SECRET_KEY")
namespace = os.getenv("NAMESPACE")
bucket_name = os.getenv("BUCKET_NAME")

# Print the configuration for debugging
print(f"MINIO_ENDPOINT: {minio_endpoint}")
print(f"ACCESS_KEY: {access_key}")
print(f"SECRET_KEY: {secret_key}")
print(f"NAMESPACE: {namespace}")
print(f"BUCKET_NAME: {bucket_name}")

# Initialize MinIO client
minio_client = Minio(
    minio_endpoint.replace("http://", "").replace("https://", ""),
    access_key=access_key,
    secret_key=secret_key,
    secure=minio_endpoint.startswith("https")
)

# Run the function
save_logs_to_minio(namespace, bucket_name, minio_client)
