#!/usr/bin/python3

from flask import Flask, jsonify
import os
import pyodbc
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv('.env')

app = Flask(__name__)

@app.route('/revenue-report', methods=['GET'])
def run_report():

    # Database connection details
    server = os.getenv('host')
    database = os.getenv('dbname')
    username = os.getenv('user')
    password = os.getenv('password')

    # Slack details
    slack_webhook_url_1 = os.getenv('webhook_product')
    slack_webhook_url_2 = os.getenv('webhook_reporting')

    image_url = 'https://domain.com/assets/img/favicon.ico'

    # Get yesterday's date
    yesterday = datetime.now() - timedelta(1)
    formatted_date = yesterday.strftime("%d.%m.%Y")

    # Connect to Azure SQL Database
    conn = pyodbc.connect('DRIVER={ODBC Driver 18 for SQL Server};SERVER=' +
                          server+';DATABASE='+database+';UID='+username+';PWD=' + password)
    cursor = conn.cursor()

    # Query data from database
    cursor.execute('''select * from report.GeneralCompanyReport order by [Order]''')

    # Find indices for 'Key' and 'Value'
    key_index = None
    value_index = None
    for index, description in enumerate(cursor.description):
        if description[0] == 'Key':
            key_index = index
        elif description[0] == 'Value':
            value_index = index

    # Check if indices are found
    if key_index is None or value_index is None:
        raise Exception("Key and/or Value columns not found in the database")

    rows = cursor.fetchall()

    # Slack message setup using blocks
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Simple Report for {formatted_date}:*"}},
        {"type": "divider"}
    ]

    # Combine rows into a single block
    report_lines = []
    for row in rows:
        key = row[key_index]
        value = row[value_index]
        report_lines.append(f"*{key}* {value}")

    combined_block = {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(report_lines)}}
    blocks.append(combined_block)

    # Sending data to Slack
    slack_data = {"blocks": blocks}
    response_product = requests.post(slack_webhook_url_1, json=slack_data)
    response_reporting = requests.post(slack_webhook_url_2, json=slack_data)

    if response_product.status_code == 200 and response_reporting.status_code == 200:
        return jsonify({"message": "Data sent to Slack successfully"})
    else:
        return jsonify({"error": f"Error sending data to Slack: {response.status_code}"}), 500

    # Close the database connection
    cursor.close()
    conn.close()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
