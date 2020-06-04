#!/usr/bin/python env

import os
import subprocess
import re
import requests
import json

from flask import Flask, request, jsonify
from flask_httpauth import HTTPBasicAuth
from os.path import join, dirname
from dotenv import load_dotenv

app = Flask(__name__)
auth = HTTPBasicAuth()
dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

users = {os.environ["username"]: os.environ["password"]}

@auth.get_password
def get_pw(username):
    if username in users:
        return users.get(username)
    return None


def iptables_vpn(allow_ip, port, provider, comment, dest_ip, dest_port):

    search = subprocess.Popen('iptables -t nat -S | grep %s' % port, stdout=subprocess.PIPE, stderr=None, shell=True).communicate()
    output = search[0].decode("utf-8").rstrip()[3:]

    rules = ['iptables -t nat -D %s' % output,
             'iptables -t nat -A PREROUTING -d %s/32 -p tcp -m tcp --dport %s -m comment --comment "%s %s" -j DNAT ' \
             '--to-destination %s:%s' % (allow_ip, port, provider, comment, dest_ip, dest_port)]

    for rule in rules:
        if re.search('PREROUTING', rule):
            subprocess.Popen(rule, stdout=subprocess.PIPE, stderr=None, shell=True)


def office_vpn(port, provider, office_ip, dest_port, comment):

    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}

    iptables_data = {
        "allow_ip": '10.8.0.10',
        "port": port,
        "provider": provider,
        "office_ip": office_ip,
        "dest_port": dest_port,
        "comment": comment
    }

    jsonData = json.dumps(iptables_data)

    requests.post('http://10.8.0.10:5000/callbacks/', jsonData, headers=headers, auth=(os.environ["username"], os.environ["client_vpn_pass"]))

@app.route('/callbacks/', methods=['POST'])
@auth.login_required

def callbacks():

    data = request.json

    allow_ip = data['allow_ip']
    port = data['port']
    provider = data['provider']
    comment = data['comment']
    dest_ip = data['dest_ip']
    dest_port = data['dest_port']
    office = data['office']

    if office == '1':
        office_ip = dest_ip
        iptables_vpn(allow_ip, port, provider, comment, dest_ip='10.8.0.10', dest_port=port)
        office_vpn(port, provider, office_ip, dest_port, comment)
    elif office == '0':
        iptables_vpn(allow_ip, port, provider, comment, dest_ip, dest_port)
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
