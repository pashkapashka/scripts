#!/usr/bin/python3

from flask import Flask, jsonify
import os
import psycopg2
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv('.env')

app = Flask(__name__)


@app.route('/internal-report', methods=['GET'])
def run_report():

    # Slack details
    slack_webhook_url = os.getenv('webhook')

    # Get yesterday's date
    yesterday = datetime.now() - timedelta(1)
    formatted_date = yesterday.strftime("%d.%m.%Y")

    # Connect to Azure PostgreSQL Database
    conn = psycopg2.connect(
        host=os.getenv('host'),
        dbname=os.getenv('dbname'),
        user=os.getenv('user'),
        password=os.getenv('password')
    )
    cursor = conn.cursor()

    # Query data from database
    cursor.execute('''select * from int_report_view.PavelReport''')

    rows = cursor.fetchall()

    # Slack message setup using blocks
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Internal Report:*"}},
        {"type": "divider"}
    ]

    # Combine rows into a single block
    report_lines = []
    for row in rows:
        # Assuming 'Key' is the second column and 'Value' is the third column
        key = row[1]
        value = row[2]
        report_lines.append(f"*{key}:* {value}")

    combined_block = {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(report_lines)}}
    blocks.append(combined_block)

    # Sending data to Slack
    slack_data = {"blocks": blocks}
    response = requests.post(slack_webhook_url, json=slack_data)

    if response.status_code == 200:
        return jsonify({"message": "Data sent to Slack successfully"})
    else:
        return jsonify({"error": f"Error sending data to Slack: {response.status_code}"}), 500

    # Close the database connection
    cursor.close()
    conn.close()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
