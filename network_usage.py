#!/usr/bin/python3

import os
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from flask import Flask, Response
from prometheus_client import Counter, generate_latest
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

subscription_ids = [
    os.getenv('AZURE_SUBSCRIPTION_ID_UAT'),
    os.getenv('AZURE_SUBSCRIPTION_ID_FINANCE'),
    os.getenv('AZURE_SUBSCRIPTION_ID_PROD')
]
client_id = os.getenv('AZURE_CLIENT_ID')
client_secret = os.getenv('AZURE_CLIENT_SECRET')
tenant_id = os.getenv('AZURE_TENANT_ID')

credential = ClientSecretCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    client_secret=client_secret
)

app = Flask(__name__)

network_in_metric = Counter('network_in_bytes_total', 'Total incoming network traffic in bytes', ['vm_id', 'subscription_id'])
network_out_metric = Counter('network_out_bytes_total', 'Total outgoing network traffic in bytes', ['vm_id', 'subscription_id'])

@app.route('/metrics')
def metrics():
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=1)  # Adjust the time span as needed

    for subscription_id in subscription_ids:
        compute_client = ComputeManagementClient(credential, subscription_id)
        monitor_client = MonitorManagementClient(credential, subscription_id)

        # Retrieve all VMs for the subscription
        vms = compute_client.virtual_machines.list_all()
        for vm in vms:
            vm_id = vm.id.split('/')[-1]
            resource_group = vm.id.split('/')[4]

            # Query Azure Monitor API
            metrics_data = monitor_client.metrics.list(
                resource_uri=f"subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_id}",
                timespan="{}/{}".format(start_time.isoformat(), end_time.isoformat()),
                interval='PT1H',
                metricnames='Network In Total,Network Out Total',
                aggregation='Total'
            )

            for item in metrics_data.value:
                # Update Prometheus counters with the retrieved data
                if item.name.value == 'Network In Total':
                    network_in_metric.labels(vm_id=vm_id, subscription_id=subscription_id).inc(item.timeseries[0].data[0].total)
                elif item.name.value == 'Network Out Total':
                    network_out_metric.labels(vm_id=vm_id, subscription_id=subscription_id).inc(item.timeseries[0].data[0].total)

    return Response(generate_latest(), mimetype="text/plain")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5999)
