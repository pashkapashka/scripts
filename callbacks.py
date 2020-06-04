#!/usr/bin/python env

import os
import json, requests
import re
import subprocess
import socket

from flask import Flask, request, jsonify, abort
from flask_httpauth import HTTPBasicAuth
from slack import WebClient
from slack.errors import SlackApiError
from dotenv import load_dotenv
from pathlib import Path

env_path = Path('/srv/callbacks') / '.env'
load_dotenv(dotenv_path=env_path)
slack_api_token = os.environ["SLACK_API_TOKEN"]

app = Flask(__name__)
auth = HTTPBasicAuth()
client = WebClient(token=slack_api_token)
users = {os.environ["username"]: os.environ["password"]}

list_providers = ['soft1', 'soft2', 'simple', 'list', 'provider1', 'provider2', 'provider3']
d = {}

for (ports, providers) in zip(range(8840, 8847), list_providers):
    d[providers] = ports

allow_ip = '127.0.0.1'

@auth.get_password
def get_pw(username):
    if username in users:
        return users.get(username)
    return None

@app.before_request
def limit_remote_addr():
    if request.remote_addr != '127.0.0.1':
        abort(403)

def is_valid_ipv4_address(address):
    try:
        socket.inet_pton(socket.AF_INET, address)
    except AttributeError:
        try:
            socket.inet_aton(address)
        except socket.error:
            return None
        return address.count('.') == 3
    except socket.error:
        return None
    return address

def is_valid_port(port):
    try:
        if 1 <= int(port) <= 65535:
            return port
        else:
            raise ValueError
    except ValueError:
        return False

def validate(data):
    if {'provider', 'env', 'dest_ip', 'dest_port', 'comment', 'office'} != set(data.keys()):
        abort(400)
    if data['provider'] not in d.keys():
        abort(400)
    if data['office'] not in ['1', '0']:
        abort(400)

def iptables_vpn(allow_ip, port, provider, dest_ip, dest_port, comment, office):

    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}

    iptables_data = {
        "allow_ip": allow_ip,
        "port": port,
        "provider": provider,
        "dest_ip": dest_ip,
        "dest_port": dest_port,
        "comment": comment,
        "office": office
    }

    jsonData = json.dumps(iptables_data)

    requests.post('http://%s:5000/callbacks/' % allow_ip, jsonData, headers=headers, auth=(os.environ["username"], os.environ["client_vpn_pass"]))

def slack_notify(client, provider, env, comment):
    try:
        response = client.chat_postMessage(
            channel='#callbacks',
            as_user=True,
            text="Provider: %s, environment: %s, comment: %s" % (provider, env, comment))
        assert response["message"]["text"] == "Provider: %s, environment: %s, comment: %s" % (provider, env, comment)
    except SlackApiError as e:
        assert e.response["ok"] is False
        assert e.response["error"]
        print(f"Got an error: {e.response['error']}")


def nginx_reload():
    try:
        nginx_check = subprocess.check_output(['nginx', '-t'], stderr=subprocess.STDOUT)
        for check in nginx_check.splitlines():
            status = check.decode("utf-8")
            if re.search('successful', status):
                subprocess.call('nginx -s reload', shell=True)
    except subprocess.CalledProcessError as e:
        error = "command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output.decode('utf-8'))
        print(error)


def toggle(config, env):
    with open(config, 'r') as f:
        file_data = f.read()
    if env == 'dev':
        if re.findall(r'# proxy_pass http:\/\/127\.0\.0\.1', file_data):
            file_data = re.sub(r'try_files', '# try_files', file_data)
            file_data = re.sub(r'# proxy_pass http:\/\/127\.0\.0\.1', 'proxy_pass http://127.0.0.1', file_data)
    elif env == 'stage':
        if re.findall(r'# try_files', file_data):
            file_data = re.sub(r'# try_files', 'try_files', file_data)
            file_data = re.sub(r'proxy_pass http:\/\/127\.0\.0\.1', '# proxy_pass http://127.0.0.1', file_data)
    with open(config, 'w') as f:
        f.write(file_data)


@app.route('/callbacks/', methods=['POST'])
@auth.login_required

def callbacks():
    data = request.json
    dest_ip = is_valid_ipv4_address(address=data['dest_ip'])
    dest_port = is_valid_port(port=data['dest_port'])
    validate(data)
    port = d[data['provider']]
    provider = data['provider']
    comment = data['comment']
    env = data['env']
    office = data['office']
    config = '/etc/nginx/callbacks/%s.conf' % provider
    toggle(config, env)
    nginx_reload()

    if env == 'dev':
        iptables_vpn(allow_ip, port, provider, dest_ip, dest_port, comment, office)
        slack_notify(client, provider, env, comment)
    elif env == 'stage':
        iptables_vpn(allow_ip, port, provider, dest_ip='', dest_port='', comment='', office='0')
        slack_notify(client, provider, env, comment='dev/stage server')

    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
