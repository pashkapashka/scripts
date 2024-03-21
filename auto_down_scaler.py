#!/usr/bin/env python3

from datetime import datetime
from kubernetes import client, config


def context_detection():
    contexts, active_context = config.list_kube_config_contexts()
    if not contexts:
        print("Cannot find any context in kube-config file.")
        return
    contexts = [context['name'] for context in contexts]
    return contexts


prod = client.CoreV1Api(api_client=config.new_client_from_config(context=context_detection()[0]))
prod_scale = client.AppsV1Api(api_client=config.new_client_from_config(context=context_detection()[0]))
resp = prod.list_namespaced_pod(namespace='vpn')
body = {"spec": {"replicas": 0}}

for describe_pods in resp.items:
    if describe_pods.metadata.labels['app'] == 'pritunl-vpn':
        start_time = describe_pods.status.start_time
        start_time = str(start_time)[:-6]
        start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
        start_time = datetime(start_time.year, start_time.month, start_time.day, start_time.hour, start_time.minute,
                              start_time.second)
        delta = datetime.now() - start_time
        if round(delta.total_seconds() / 60) >= 15:
            prod_scale.patch_namespaced_deployment_scale(name='pritunl-vpn', namespace='vpn', body=body)
            print('pritunl-vpn downscaled')
        else:
           print('pritunl-vpn online')
