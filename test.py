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


# Load Kubernetes configuration
config.load_kube_config(config_file=os.getenv("KUBECONFIG_FILE"))

# Create Kubernetes API client
v1 = client.CoreV1Api()

# Path to the YAML file
yaml_file_path = "stored_times.yaml"

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
        print("now ----",now)
        # Load the stored time from the YAML
        stored_times = load_stored_times()
        stored_time_str = stored_times.get(namespace, {}).get(pod_name, {}).get(container_name, None)
        print("stored_time_str ----",stored_time_str)
        # If stored_time_str is not available, fetch all logs
        if stored_time_str:
            try:
                stored_time = datetime.datetime.strptime(stored_time_str, "%Y-%m-%dT%H:%M:%S.%f%z")
            except ValueError:
                # Fallback in case of a parsing error
                stored_time = now
            since_seconds = int((now - stored_time).total_seconds())
            print("old time -- " + str(stored_time))
            try: 
               log = v1.read_namespaced_pod_log(name=pod_name, namespace=namespace, container=container_name, since_seconds=since_seconds)
            except ApiException as e:
                print("didn't get logs !!")
                if e.status == 404:
                    print(f"Pod '{pod_name}' not found in namespace '{namespace}'. Skipping...")
                else:
                    print(f"Error fetching logs for pod '{pod_name}' in namespace '{namespace}': {e}")
                return
        else:
            try:
                log = v1.read_namespaced_pod_log(name=pod_name, namespace=namespace, container=container_name)
            except ApiException as e:
                print("didn't get logs !!")
                if e.status == 404:
                    print(f"Pod '{pod_name}' not found in namespace '{namespace}'. Skipping...")
                else:
                    print(f"Error fetching logs for pod '{pod_name}' in namespace '{namespace}': {e}")
                return

        # Print the logs
        print(f"Logs for pod '{pod_name}', container '{container_name}': '{stored_time_str}' to '{str(now)}'")
        # print(log)

        # Define the MinIO object name (path)
        date_str = now.strftime("%d-%m-%Y")
        time_str = now.strftime("%H-%M-%S")
        object_name = f"{namespace}/{container_name}/{pod_name}/{date_str}/{time_str}.log"

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

        # Update the YAML with the new time after fetching logs
        update_stored_times(namespace, pod_name, container_name, now.isoformat())

        # Sleep for 60 seconds
        time.sleep(60)
        print("--------")

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

# Environment variables
minio_endpoint = os.getenv("MINIO_ENDPOINT")
access_key = os.getenv("MINIO_ACCESS_KEY")
secret_key = os.getenv("MINIO_SECRET_KEY")
namespace = os.getenv("NAMESPACE")
bucket_name = os.getenv("BUCKET_NAME")

# Initialize MinIO client
minio_client = Minio(
    minio_endpoint.replace("http://", "").replace("https://", ""),
    access_key=access_key,
    secret_key=secret_key,
    secure=minio_endpoint.startswith("https")
)

def monitor_pods_and_save_logs(namespace, bucket_name, minio_client):
    processed_pods = set()  # Keep track of already processed pods
    
    while True:
        pods = v1.list_namespaced_pod(namespace)
        threads = []

        for pod in pods.items:
            pod_name = pod.metadata.name

            # If the pod is already processed, skip it
            if pod_name in processed_pods:
                continue

            # Mark the pod as processed
            processed_pods.add(pod_name)

            # Start a new thread for each container in the new pod
            for container in pod.spec.containers:
                container_name = container.name
                thread = threading.Thread(target=save_logs_for_container, args=(namespace, bucket_name, minio_client, pod_name, container_name))
                threads.append(thread)
                thread.start()

        # Sleep for a bit before checking for new pods
        time.sleep(30)  # Adjust the interval as needed

    # Optionally, you can join threads or handle stopping conditions.
    for thread in threads:
        thread.join()

# Run the monitoring function
monitor_pods_and_save_logs(namespace, bucket_name, minio_client)
