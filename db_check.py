#!/usr/bin/python3 env

import prometheus_client, psycopg, os, requests
from prometheus_client import Gauge, CollectorRegistry
from flask import Response, Flask
from dotenv import load_dotenv
from pathlib import Path
from psycopg.rows import dict_row

# load app
app = Flask(__name__)

# load env
dotenv_path = Path('.env')
load_dotenv()

# credentials
name = os.getenv('DB_NAME')
user = os.getenv('DB_USER')
password = os.getenv('DB_PASSWORD')
host = os.getenv('DB_HOST')


headers = {'accept': 'text/plain'}
verificationTokenUrl = 'https://domain.com/v3/signin/StartEmailLogin'
refreshTokenUrl = 'https://domain.com/v3/signin/ConfirmEmailLogin'
refreshTokenUrlNew = 'https://domain.com/v3/RefreshToken'
email = os.getenv('SIMPLE_EMAIL')


def balance_history(token):

    params = {
        'assetId': 'USDT',
        'batchSize': '1',
    }

    response = requests.get('https://domain.com/api/v3/history', params=params, headers=token)
    return response


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

# queries
request = "select * from int_report_view.check_connect_status"
info_max_connections = "select max_conn,used,res_for_super,max_conn-used-res_for_super res_for_normal \
                        from (select count(*) used from pg_stat_activity) t1, (select setting::int res_for_super \
                        from pg_settings where name=$$superuser_reserved_connections$$) t2, \
                        (select setting::int max_conn from pg_settings where name=$$max_connections$$) t3;"

# prometheus counter
COUNTER_DB = Gauge('microservice_check_db', 'Base Gauge', ['microservice', 'type'], registry=CollectorRegistry())
COUNTER_CONNECTIONS = Gauge('check_max_connections', 'Base Gauge',
                            ['type'], registry=CollectorRegistry())


connect = psycopg.connect(dbname=name, user=user, password=password, host=host, sslmode='require')
def check_db(check_db_status):
    COUNTER_DB.clear()
    connect = psycopg.connect(dbname=name, user=user, password=password, host=host)
    with connect.cursor(row_factory=dict_row) as current:
        current.execute(check_db_status)
        for record in current:
            COUNTER_DB.labels(microservice=record['app_name'], type=record['type']).set(int(1))
        current.close()


def check_max_connections(max_connections):
    COUNTER_CONNECTIONS.clear()
    connect = psycopg.connect(dbname=name, user=user, password=password, host=host)
    with connect.cursor(row_factory=dict_row) as current:
        current.execute(max_connections)
        for record in current:
            counter_records = {'max_conn': record['max_conn'], 'used': record['used'], 'free_for_superusers': record['res_for_super'], 'free_for_users': record['res_for_normal']}
            for key, value in counter_records.items():
                COUNTER_CONNECTIONS.labels(type=key).inc(value)
        current.close()


@app.route("/check_db")
def db_check():
    token_data = generate_headers()
    balance_history(token_data)
    check_db(request)
    return Response(prometheus_client.generate_latest(COUNTER_DB), mimetype="text/plain")


@app.route("/check_max_connections")
def db_check_connections():
    check_max_connections(info_max_connections)
    return Response(prometheus_client.generate_latest(COUNTER_CONNECTIONS), mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5454, debug=True)
