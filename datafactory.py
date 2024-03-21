#!/usr/bin/python3

import os, prometheus_client
from dotenv import load_dotenv
from pathlib import Path
from azure.identity import ClientSecretCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
from azure.mgmt.datafactory.models import *
from datetime import datetime, timezone, timedelta
from prometheus_client import Gauge, CollectorRegistry
from flask import Response, Flask


# load env
dotenv_path = Path('.env')
load_dotenv()

app = Flask(__name__)
auth = ClientSecretCredential(client_id=os.getenv('CLIENT_ID'), client_secret=os.getenv('CLIENT_SECRET'), tenant_id=os.getenv('TENANT_ID'))
params = RunFilterParameters(last_updated_after=datetime.now(timezone.utc) - timedelta(1), last_updated_before=datetime.now(timezone.utc) + timedelta(1))


COUNTER = Gauge('pipelines', 'Base Gauge', ['run_id', 'name', 'status'], registry=CollectorRegistry())


def return_status_pipeline(credentials, filter_params, df_name, rg_name, subscription_id):
    adf_client = DataFactoryManagementClient(credentials, subscription_id)
    pipeline_runs = adf_client.pipeline_runs.query_by_factory(rg_name, df_name, filter_params)
    for pipeline_run in pipeline_runs.value:
        get_pipeline_info = adf_client.pipeline_runs.get(rg_name, df_name, pipeline_run.run_id)
        status = 1 if get_pipeline_info.status == 'Succeeded' or get_pipeline_info.status == 'In progress' or get_pipeline_info.status == 'Queued' or get_pipeline_info.status == 'Cancelled' else 0
        COUNTER.labels(run_id=get_pipeline_info.run_id, name=get_pipeline_info.pipeline_name, status=get_pipeline_info.status).set(int(status))


@app.route("/metrics")
def r_value():
    return_status_pipeline(auth, params, os.getenv('DATAFACTORY'), os.getenv('RESOURCEGROUP'), os.getenv('SUBSCRIPTION_ID'))
    return Response(prometheus_client.generate_latest(COUNTER), mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9999)
