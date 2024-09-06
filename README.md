# logminder-extractor


export POD_NAME=$(kubectl get pods --namespace minio -l "release=minio" -o jsonpath="{.items[0].metadata.name}")
kubectl port-forward $POD_NAME 9000 --namespace minio 
 
 
 kubectl port-forward svc/minio-console 32665:9001 --namespace minio

source venv/bin/activate   

 export MINIO_ENDPOINT='http://localhost:9000'                                                
export MINIO_ACCESS_KEY='IDkRUkP1W8Qfk66e9Xkm'
export MINIO_SECRET_KEY='EFy662A4iCFN1JEhT6fFFLUcgMBS5NSpRpw49ciA'
export NAMESPACE='test-ns'                                                                 
export BUCKET_NAME='local'
export KUBECONFIG_FILE='/Users/jatinjangir/Documents/course/CS685/project/logminder/config'