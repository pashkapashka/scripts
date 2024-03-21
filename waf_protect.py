#!/usr/local/bin/python3.11 env

import requests
import json
import os
import sys
from dotenv import load_dotenv
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch


class ElasticSearchClient:
    def __init__(self, url, auth):
        self.client = Elasticsearch(url, basic_auth=auth)

    def search(self, index, body):
        return self.client.search(index=index, body=body, ignore=404)


class CloudflareAPI:
    def __init__(self, token):
        self.token = token
        self.base_url = "https://api.cloudflare.com/client/v4"

    def block_ip_addresses(self, zone_id, ruleset_id, rule_id, ip_addresses):
        url = f"{self.base_url}/zones/{zone_id}/rulesets/{ruleset_id}/rules/{rule_id}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        expression = " or ".join([f"(ip.src eq {ip})" for ip in ip_addresses])
        data = {
            "action": "block",
            "expression": expression,
            "description": "BLOCK"
        }
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code == 200:
            print("WAF rules updated")
        else:
            print(f"Error code: {response.status_code}")
            print(response.json())


class LogProcessor:
    def __init__(self, es_client, cf_api, ip_addresses_file, json_query_file):
        self.es_client = es_client
        self.cf_api = cf_api
        self.ip_addresses_file = ip_addresses_file
        self.json_query_file = json_query_file

    def process_logs(self, zone_id, ruleset_id, rule_id):
        current_date = datetime.now().strftime('%Y-%m-%d')
        index = f'api-trace-jet-logs-prod-{current_date}'

        with open(self.ip_addresses_file, "r") as file:
            ip_addresses_data = json.load(file)
            ip_addresses = ip_addresses_data["ip_addresses"]

        with open(self.json_query_file, "r") as file:
            json_query = json.load(file)

        start_time, end_time = self.get_time_range()
        json_query["query"]["bool"]["filter"][1]["range"]["@timestamp"]["gte"] = start_time
        json_query["query"]["bool"]["filter"][1]["range"]["@timestamp"]["lte"] = end_time

        result = self.es_client.search(index=index, body=json_query)

        print('Logs for the last hour:\n')

        ip_list = []
        clients = {}
        for index_info in result['hits']['hits']:
            ip_address_list = index_info['fields'].get('iP', [])
            dateTime = index_info['fields'].get('dateTime')
            rejectCode = index_info['fields'].get('rejectCode')

            iPCountry = index_info['fields'].get('iPCountry')
            iP = index_info['fields'].get('iP')
            clientId = index_info['fields'].get('clientId')

            if ip_address_list:
                ip_list.append(ip_address_list[0])
                clients[ip_address_list[0]] = clientId if clientId else None
            print(f"Datetime: {dateTime}, Country: {iPCountry}, IP: {iP}, ClientID: {clientId if clientId else None}, RejectCode: {rejectCode}")

        ip_counts = {}
        for ip_address in ip_list:
            ip_counts[ip_address] = ip_counts.get(ip_address, 0) + 1

        ip_addresses_to_add = set()
        with open('ruleset.log', 'a') as file:
            for ip_address, count in ip_counts.items():
                if count >= 5:
                    ip_addresses_to_add.add(ip_address)
                    log_message = f"Datetime: {datetime.now()}, Blocked: {ip_address}, ClientID: {clients[ip_address]}"
                    file.write(log_message + '\n')

        with open(self.ip_addresses_file, 'r') as file:
            data = json.load(file)
            existing_ip_addresses = set(data['ip_addresses'])

        with open(self.ip_addresses_file, 'w') as file:
            data['ip_addresses'] = list(existing_ip_addresses.union(ip_addresses_to_add))
            json.dump(data, file, indent=2)

        self.cf_api.block_ip_addresses(zone_id=zone_id, ruleset_id=ruleset_id, rule_id=rule_id, ip_addresses=ip_addresses)

    @staticmethod
    def get_time_range(hours=1):
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        return start_time.strftime("%Y-%m-%dT%H:%M:%S"), end_time.strftime("%Y-%m-%dT%H:%M:%S")


if __name__ == '__main__':
    load_dotenv('.env')

    es_url = os.getenv('ES_URL')
    es_auth = (os.getenv('ES_USERNAME'), os.getenv('ES_PASSWORD'))
    es_client = ElasticSearchClient(url=es_url, auth=es_auth)

    cf_token = os.getenv('CF_TOKEN')
    cf_api = CloudflareAPI(token=cf_token)

    log_processor = LogProcessor(
        es_client=es_client,
        cf_api=cf_api,
        ip_addresses_file='ip_addresses.json',
        json_query_file='json_query.json'
    )

    log_processor.process_logs(
        zone_id=os.getenv('CF_ZONE_ID'),
        ruleset_id=os.getenv('CF_RULESET_ID'),
        rule_id=os.getenv('CF_RULE_ID')
    )
