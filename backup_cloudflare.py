#!/usr/bin/python3 env

import argparse
import CloudFlare
import json
import os
from datetime import datetime, timedelta
import yaml

# load config
with open('config.yml', 'r') as yaml_file:
    config = yaml.safe_load(yaml_file)

def get_zone_info(name):
    for entry in config:
        if entry['name'] == name:
            return entry.get('api_key'), entry.get('zone_name')
    return None, None

def backup_dns_records(domain_name, backup_name):
    api_key, zone_name = get_zone_info(domain_name)

    if api_key is None or zone_name is None:
        exit(f'Configuration not found for domain: {domain_name}')

    cf = CloudFlare.CloudFlare(token=api_key)

    try:
        zones = cf.zones.get(params={'name': zone_name, 'per_page': 1})
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit(f'/zones.get {e} - API call failed')
    except Exception as e:
        exit(f'/zones.get - {e} - API call failed')

    if len(zones) == 0:
        exit(f'No zones found for domain: {domain_name}')

    zone = zones[0]
    zone_id = zone['id']

    try:
        dns_records = cf.zones.dns_records.get(zone_id)
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit(f'/zones/dns_records.get {e} - API call failed')

    # Create a list to store DNS records
    dns_records_list = []

    for dns_record in dns_records:
        r_name = dns_record['name']
        r_type = dns_record['type']
        r_value = dns_record['content']
        r_id = dns_record['id']
        r_proxied = dns_record['proxied']
        dns_records_list.append({'id': r_id, 'name': r_name, 'type': r_type, 'value': r_value, 'proxied': r_proxied})

    # Create a folder for backups if it doesn't exist
    backup_folder = os.path.join('backups', domain_name)
    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)

    # Create a filename for the backup
    current_datetime = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    backup_filename = f'{backup_name}_{current_datetime}.json'

    backup_file_path = os.path.join(backup_folder, backup_filename)

    # Save the DNS records to a JSON file
    with open(backup_file_path, 'w') as json_file:
        json.dump(dns_records_list, json_file, indent=4)

    print(f'DNS records from {zone_name} zone backed up to {backup_filename}')

    # Delete old backups (older than 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    for backup_file in os.listdir(backup_folder):
        file_parts = os.path.splitext(backup_file)[0].split('_')
        if len(file_parts) >= 2:
            file_datetime_str = "_".join(file_parts[1:])
            file_datetime = datetime.strptime(file_datetime_str, '%Y_%m_%d_%H_%M_%S')
            if file_datetime < thirty_days_ago:
                file_path = os.path.join(backup_folder, backup_file)
                os.remove(file_path)


def restore_dns_records(domain_name, backup_name, input_file):
    api_key, zone_name = get_zone_info(domain_name)

    if api_key is None or zone_name is None:
        exit(f'Configuration not found for domain: {domain_name}')

    cf = CloudFlare.CloudFlare(token=api_key)

    try:
        zones = cf.zones.get(params={'name': zone_name, 'per_page': 1})
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit(f'/zones.get {e} - API call failed')
    except Exception as e:
        exit(f'/zones.get - {e} - API call failed')

    if len(zones) == 0:
        exit(f'No zones found for domain: {domain_name}')

    zone = zones[0]
    zone_id = zone['id']

    # Load DNS records from the input JSON file
    if not os.path.exists(input_file):
        exit(f'Backup file {input_file} does not exist.')

    with open(input_file, 'r') as json_file:
        dns_records_list = json.load(json_file)

    # Delete existing DNS records in the zone
    dns_records = cf.zones.dns_records.get(zone_id)
    for dns_record in dns_records:
        dns_record_id = dns_record['id']
        try:
            cf.zones.dns_records.delete(zone_id, dns_record_id)
        except CloudFlare.exceptions.CloudFlareAPIError as e:
            print(f'Failed to delete DNS record {dns_record_id}: {e}')

    # Create DNS records from the input file
    for dns_record_data in dns_records_list:
        try:
            cf.zones.dns_records.post(
                zone_id,
                data={
                    'name': dns_record_data['name'],
                    'type': dns_record_data['type'],
                    'content': dns_record_data['value'],
                    'proxied': dns_record_data['proxied'],
                },
            )
        except CloudFlare.exceptions.CloudFlareAPIError as e:
            print(f'Failed to create DNS record: {e}')

    print(f'DNS records in {zone_name} zone restored from {input_file}')



def check_dns_records(domain_name, backup_name):
    api_key, zone_name = get_zone_info(domain_name)

    if api_key is None or zone_name is None:
        exit(f'Configuration not found for domain: {domain_name}')

    cf = CloudFlare.CloudFlare(token=api_key)

    try:
        zones = cf.zones.get(params={'name': zone_name, 'per_page': 1})
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit(f'/zones.get {e} - API call failed')
    except Exception as e:
        exit(f'/zones.get - {e} - API call failed')

    if len(zones) == 0:
        exit(f'No zones found for domain: {domain_name}')

    zone = zones[0]
    zone_id = zone['id']

    try:
        dns_records = cf.zones.dns_records.get(zone_id)
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit(f'/zones/dns_records.get {e} - API call failed')

    backup_folder = os.path.join('backups', domain_name)
    backup_files = [f for f in os.listdir(backup_folder) if f.startswith(backup_name) and f.endswith('.json')]
    if not backup_files:
        exit(f'No backup files found for {backup_name} in {backup_folder}')

    latest_backup_file = max(backup_files)

    with open(os.path.join(backup_folder, latest_backup_file), 'r') as json_file:
        latest_dns_records_list = json.load(json_file)

    latest_dns_records_dict = {(record['name'], record['type']): record for record in latest_dns_records_list}

    added_records = []
    updated_records = []
    removed_records = []

    for dns_record in dns_records:
        r_name = dns_record['name']
        r_type = dns_record['type']
        r_value = dns_record['content']
        key = (r_name, r_type)

        if key in latest_dns_records_dict:
            latest_record = latest_dns_records_dict[key]
            if latest_record['value'] != r_value:
                updated_records.append(f'Updated: {r_name} ({r_type} -> {latest_record["type"]}, {r_value} -> {latest_record["value"]})')
        else:
            added_records.append(f'Added: {r_name} ({r_type}, {r_value})')

    for (name, record_type), record in latest_dns_records_dict.items():
        key = (name, record_type)
        if key not in {(dns_record['name'], dns_record['type']) for dns_record in dns_records}:
            removed_records.append(f'Removed: {name} ({record_type}, {record["value"]})')

    if added_records:
        print('Added records:')
        for record in added_records:
            print(record)

    if updated_records:
        print('Updated records:')
        for record in updated_records:
            print(record)

    if removed_records:
        print('Removed records:')
        for record in removed_records:
            print(record)

    if not added_records and not updated_records and not removed_records:
        print('No differences found between current DNS records and the latest backup.')

def backup_all_domains():
    for entry in config:
        backup_dns_records(entry['name'], entry['name'])

def check_all_domains():
    for entry in config:
        check_dns_records(entry['name'], entry['name'])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Cloudflare DNS Management Script')
    parser.add_argument('--backup', action='store_true', help='Create a DNS records backup')
    parser.add_argument('--restore', action='store_true', help='Restore DNS records to the same account')
    parser.add_argument('--name', type=str, help='Specify the name of the backup or domain for restore/check')
    parser.add_argument('--path-to-restore', type=str, help='Specify the path to the backup file for restore')
    parser.add_argument('--check', action='store_true', help='Check DNS records against the latest backup')
    parser.add_argument('--all', action='store_true', help='Backup/Restore/Check all domains in the configuration')

    args = parser.parse_args()

    if args.backup and args.name:
        backup_dns_records(args.name, args.name)

    if args.restore and args.name and args.path_to_restore:
        restore_dns_records(args.name, args.name, args.path_to_restore)

    if args.check and args.name:
        check_dns_records(args.name, args.name)

    if args.all:
        backup_all_domains()
