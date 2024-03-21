#!/usr/bin/python3 env

import os, sys, getopt
from azure.keyvault.secrets import SecretClient
from azure.identity import ClientSecretCredential
from kubernetes import client, config
from dotenv import load_dotenv
from pathlib import Path
from kubernetes.client.rest import ApiException
import traceback
from pprint import pprint

# load env
dotenv_path = Path('.env')
load_dotenv()

# kubernetes config
config.load_kube_config()
v1 = client.CoreV1Api()
secret = v1.read_namespaced_secret("simple-trading-secrets", namespace='spot-services').data

# azure auth to service principal stop-access
tenant_id = os.getenv('TENANT_ID')
client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')
credential = ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret)
vault_url = os.getenv('VAULT_URL')

# vault auth
secret_client = SecretClient(vault_url=vault_url, credential=credential)

# storage data from vault to k8s
storage = {}


def sync_secret(key, value):
    vault_secret = secret_client.set_secret(key, value)
    return vault_secret.name


def get_secret(key):
    vault_secret = secret_client.get_secret(key)
    return {vault_secret.name: vault_secret.value}


def delete_secret(key):
    vault_secret = secret_client.begin_delete_secret(key).result()
    return vault_secret.name


def list_secret():
    secrets = []
    secret_properties = secret_client.list_properties_of_secrets()
    for secret_property in secret_properties:
        secrets.append(secret_property.name)
    return secrets


def restore_secret(namespace):
    dry_run = None
    pretty = 'true'
    secret_name = 'simple-trading-secrets'
    body = client.V1Secret()
    body.api_version = 'v1'
    body.data = storage
    body.kind = 'Secret'
    body.metadata = {'name': secret_name}
    body.type = 'Opaque'

    try:
        if dry_run is not None:
            api_response = v1.create_namespaced_secret(namespace, body, pretty=pretty, dry_run=dry_run)
        else:
            api_response = v1.create_namespaced_secret(namespace, body, pretty=pretty)
        pprint(api_response)
    except ApiException as e:
        print("%s" % (str(e)))
        traceback.print_exc()
        raise


if __name__ == "__main__":

    try:
        options, remainder = getopt.getopt(sys.argv[1:], 'f', ['function='])
        for opt, arg in options:
            if opt in ('-f', '--function'):
                if arg in ['sync', 'list']:
                    for k8s_key, k8s_value in secret.items():
                        functions = {'sync': sync_secret(k8s_key, k8s_value), 'list': get_secret(k8s_key)}
                        a = 'Added:' if arg == 'sync' else 'Key:'
                        print(a, functions[arg])
                if arg in ['restore']:
                    for vault_key in list_secret():
                        for k8s_key, k8s_value in get_secret(vault_key).items():
                            storage[k8s_key] = k8s_value
                    restore_secret(namespace='spot-services')
                if arg not in ['sync', 'list', 'restore']:
                    raise NameError

    except (getopt.GetoptError, NameError) as err:
        help_string = "Usage:\n./%s --sync " % sys.argv[0]
        print(help_string)
        print(err)
        sys.exit(2)
