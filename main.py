from kubernetes import client, config
from minio import Minio
from minio.error import S3Error
import os
import datetime
import io
import threading
import time
import yaml
from kubernetes.client.exceptions import ApiException

# Load the YAML file
def load_stored_times():
    if os.path.exists(yaml_file_path):
        with open(yaml_file_path, 'r') as file:
            data = yaml.safe_load(file)
            if data is None:
                return {}  # Return an empty dictionary if the YAML file is empty
            return data
    return {}  # Return an empty dictionary if the file doesn't exist

# Save the updated times to YAML
def update_stored_times(namespace, pod_name, container_name, new_time):
    stored_times = load_stored_times()
    
    # Ensure the structure exists
    if namespace not in stored_times:
        stored_times[namespace] = {}
    if pod_name not in stored_times[namespace]:
        stored_times[namespace][pod_name] = {}

    # Update the stored time for the specific container
    stored_times[namespace][pod_name][container_name] = new_time

    # Write the updated times back to the YAML file
    with open(yaml_file_path, 'w') as file:
        yaml.dump(stored_times, file)

def save_logs_for_container(namespace, bucket_name, minio_client, pod_name, container_name):
    while True:
        now = datetime.datetime.now(datetime.timezone.utc)
        print("now ----", now)
        
        # Load the stored time from the YAML
        stored_times = load_stored_times()
        stored_time_str = stored_times.get(namespace, {}).get(pod_name, {}).get(container_name, None)
        print("stored_time_str ----", stored_time_str)
        
        if stored_time_str:
            try:
                stored_time = datetime.datetime.strptime(stored_time_str, "%Y-%m-%dT%H:%M:%S.%f%z")
            except ValueError:
                # Fallback in case of a parsing error
                stored_time = now
        else:
            stored_time = None
        
        # Check if the container has restarted
        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        container_status = next(
            (status for status in pod.status.container_statuses if status.name == container_name),
            None
        )
        if container_status and container_status.restart_count > 0:
            # Get the previous container logs
            print(f"Container '{container_name}' in pod '{pod_name}' has restarted {container_status.restart_count} times.")
            
            # Get the restart time (from container's state)
            restart_time = container_status.state.terminated.finished_at if container_status.state.terminated else now
            if stored_time is None or (stored_time and restart_time > stored_time):
                print(f"Fetching previous logs from '{stored_time_str}' to '{restart_time}'")
                try:
                    previous_log = v1.read_namespaced_pod_log(
                        name=pod_name, namespace=namespace, container=container_name, previous=True
                    )
                    
                    # Define object name for previous container logs
                    date_str = restart_time.strftime("%d-%m-%Y")
                    time_str = restart_time.strftime("%H-%M-%S")
                    object_name = f"{namespace}/{pod_name}/{container_name}/previous/{date_str}/{time_str}.log"
                    
                    # Store the previous logs
                    log_data = io.BytesIO(previous_log.encode('utf-8'))
                    minio_client.put_object(
                        bucket_name=bucket_name,
                        object_name=object_name,
                        data=log_data,
                        length=len(previous_log),
                        content_type="text/plain"
                    )
                    print(f"Uploaded previous logs for container '{container_name}' in pod '{pod_name}' to MinIO at {object_name}")
                except ApiException as e:
                    print(f"Error fetching previous logs: {e}")
        
        # Fetch the current logs
        try:
            if stored_time:
                since_seconds = int((now - stored_time).total_seconds())
                log = v1.read_namespaced_pod_log(
                    name=pod_name, namespace=namespace, container=container_name, since_seconds=since_seconds
                )
            else:
                log = v1.read_namespaced_pod_log(name=pod_name, namespace=namespace, container=container_name)
        except ApiException as e:
            print("Didn't get logs!")
            if e.status == 404:
                print(f"Pod '{pod_name}' not found in namespace '{namespace}'. Skipping...")
            else:
                print(f"Error fetching logs for pod '{pod_name}' in namespace '{namespace}': {e}")
            return
        
        # Define object name for current container logs
        date_str = now.strftime("%d-%m-%Y")
        time_str = now.strftime("%H-%M-%S")
        object_name = f"{namespace}/{pod_name}/{container_name}/{date_str}/{time_str}.log"

        # Store the current logs
        log_data = io.BytesIO(log.encode('utf-8'))
        try:
            minio_client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=log_data,
                length=len(log),
                content_type="text/plain"
            )
            print(f"Uploaded current logs for container '{container_name}' in pod '{pod_name}' to MinIO at {object_name}")
        except S3Error as e:
            print(f"Error uploading to MinIO: {e}")

        # Update the YAML with the new time after fetching logs
        update_stored_times(namespace, pod_name, container_name, now.isoformat())

        # Sleep for 60 seconds
        time.sleep(log_timeout_seconds)

# Iterate through pods and create threads for each container
def save_logs_to_minio(namespace, bucket_name, minio_client):
    stored_times = load_stored_times()
    pods = v1.list_namespaced_pod(namespace)
    threads = []

    # Iterate through all the pods and containers
    for pod in pods.items:
        pod_name = pod.metadata.name
        for container in pod.spec.containers:
            container_name = container.name
            thread = threading.Thread(target=save_logs_for_container, args=(namespace, bucket_name, minio_client, pod_name, container_name))
            threads.append(thread)
            thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()


def monitor_pods_and_save_logs(bucket_name, minio_client):
    processed_pods = set()  # Keep track of already processed pods
    
    while True:
        threads = []
        if namespace_list:
            # Iterate over specified namespaces
            for namespace in namespace_list:
                pods = v1.list_namespaced_pod(namespace=namespace)
                process_pods(pods, processed_pods, namespace, bucket_name, minio_client, threads)
        else:
            # If no namespaces are specified, list pods in all namespaces
            pods = v1.list_pod_for_all_namespaces()
            process_pods(pods, processed_pods, None, bucket_name, minio_client, threads)

        # Sleep for a bit before checking for new pods
        time.sleep(pod_timeout_seconds)  # Use the timeout from the environment variable

    # Optionally, you can join threads or handle stopping conditions.
    for thread in threads:
        thread.join()

def process_pods(pods, processed_pods, namespace, bucket_name, minio_client, threads):
    for pod in pods.items:
        pod_name = pod.metadata.name
        namespace = pod.metadata.namespace  # Use this in case we're fetching from all namespaces

        # If the pod is already processed, skip it
        if pod_name in processed_pods:
            continue

        # Mark the pod as processed
        processed_pods.add(pod_name)

        # Start a new thread for each container in the pod
        for container in pod.spec.containers:
            container_name = container.name
            thread = threading.Thread(target=save_logs_for_container, args=(namespace, bucket_name, minio_client, pod_name, container_name))
            threads.append(thread)
            thread.start()


try:
    config.load_incluster_config()
    print("Loaded in-cluster Kubernetes config")
except config.ConfigException:
    # Fallback to kubeconfig if running outside the cluster (optional for local testing)
    config.load_kube_config()
    print("Loaded local kubeconfig")

# Create Kubernetes API client
v1 = client.CoreV1Api()

# Path to the YAML file
yaml_file_path = os.getenv("STORED_TIME_FILE","/app/data/stored_times.yaml")

# Environment variables
pod_timeout_seconds = int(os.getenv("POD_TIMEOUT_SECONDS", 30))
log_timeout_seconds = int(os.getenv("LOG_TIMEOUT_SECONDS", 60))
minio_endpoint = os.getenv("MINIO_ENDPOINT")
access_key = os.getenv("MINIO_ACCESS_KEY")
secret_key = os.getenv("MINIO_SECRET_KEY")
namespaces = os.getenv("NAMESPACES")
namespace_list = [ns.strip() for ns in namespaces.split(",")] if namespaces else None
bucket_name = os.getenv("BUCKET_NAME")
configmap_namespace = os.getenv("CM_NAMESPACE", "default")  # Default to 'default' namespace if not provided
configmap_name = os.getenv("CM_NAME", "logminder-extractor-config")  # Default ConfigMap name

print("pod_timeout_seconds -- ",pod_timeout_seconds)
print("log_timeout_seconds -- ",log_timeout_seconds)
print("minio_endpoint -- ",minio_endpoint)
print("access_key -- ",access_key)
print("secret_key -- ",secret_key)
print("namespaces -- ",namespaces)
print("namespace_list -- ",namespace_list)
print("bucket_name -- ",bucket_name)
print("configmap_namespace -- ",configmap_namespace)
print("configmap_name -- ",configmap_name)

# Initialize MinIO client
minio_client = Minio(
    minio_endpoint.replace("http://", "").replace("https://", ""),
    access_key=access_key,
    secret_key=secret_key,
    secure=minio_endpoint.startswith("https")
)
# Run the monitoring function
monitor_pods_and_save_logs(bucket_name, minio_client)
