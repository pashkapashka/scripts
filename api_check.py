#!/usr/bin/python3 env

import prometheus_client
from prometheus_client import Gauge, CollectorRegistry, push_to_gateway
from flask import Response, Flask
from dotenv import load_dotenv
from pathlib import Path
import requests
import yaml
import os

# load app
app = Flask(__name__)

# load env
dotenv_path = Path('.env')
load_dotenv()


headers = {'accept': 'text/plain'}
verificationTokenUrl = 'https://domain.com/test/v3/signin/StartEmailLogin'
refreshTokenUrl = 'https://domain.com/test/v3/signin/ConfirmEmailLogin'
refreshTokenUrlNew = 'https://domain.com/test/v3/RefreshToken'
email = os.getenv('SIMPLE_EMAIL')
route = 'debug/who'


def refresh_token(account):
    verificationTokenData = {'email': account, 'application': 0, 'platform': 2}
    verificationToken = requests.post(verificationTokenUrl, headers=headers, json=verificationTokenData).json()['data']['verificationToken']
    refreshTokenData = {'email': account, 'code': '000000', 'verificationToken': verificationToken}
    refreshToken = requests.post(refreshTokenUrl, headers=headers, json=refreshTokenData).json()['data']['refreshToken']
    with open('file_token', 'w+') as write_token:
        write_token.write(refreshToken)


refresh_token(email)


def generate_headers():
    with open('file_token', 'r') as read_token:
        tokens = requests.post(refreshTokenUrlNew, headers={'accept': 'text/plain'}, json={'refreshToken': read_token.read()}).json()['data']
        with open('file_token', 'w+') as write_token:
            write_token.write(tokens['refreshToken'])
        data = {'accept': 'application/json', 'Authorization': tokens['token']}
        return data


registry = CollectorRegistry()
COUNTER = Gauge('endpoints', 'Base Gauge', ['name', 'env', 'type_instance', 'type_endpoint', 'endpoint'], registry=registry)


def monitoring_api(env, type_endpoint, params, debug):
    with open("list.yaml", "r") as stream:
        data = yaml.safe_load(stream)
        for service_name in data:
            check_url = data[service_name]['env'][env][type_endpoint]
            for instance, ip in check_url.items():
                try:
                    response = requests.get('%s/%s' % (ip, debug), headers=params)
                    check_result = 1 if response.status_code == 200 else 2 if response.status_code == 401 else 0
                    COUNTER.labels(name=service_name, env=env, type_instance=instance, type_endpoint=type_endpoint, endpoint=ip).set(int(check_result))
                except:
                    COUNTER.labels(name=service_name, env=env, type_instance=instance, type_endpoint=type_endpoint, endpoint=ip).set(int(0))


@app.route("/metrics")
def r_value():
    token_data = generate_headers()
    monitoring_api('prod', 'ip_address', token_data, route)
    monitoring_api('stage', 'ip_address', token_data, route)
    monitoring_api('prod', 'url', token_data, route)
    monitoring_api('stage', 'url', token_data, route)
    push_to_gateway('pushgateway:9091', job='pushgateway', registry=registry)
    return ('Metrics sent to pushgateway')


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9999, debug=True)
