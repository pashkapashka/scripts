#!/usr/bin/python3


from datetime import datetime, timedelta
from flask import Flask, jsonify
import os
import requests
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from elasticsearch.exceptions import NotFoundError
from dotenv import load_dotenv
load_dotenv('.env')

app = Flask(__name__)

slack_webhook_url = os.getenv('webhook')

cloud_id = os.getenv('cloud_id')
cloud_auth = (os.getenv('user'), os.getenv('password'))

es = Elasticsearch(
    cloud_id=cloud_id,
    basic_auth=cloud_auth
)


@app.route('/elastic-report', methods=['GET'])
def send_to_slack():
    # Define the index name based on yesterday's date
    yesterday_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    index_name = f"api-trace-jet-logs-prod-{yesterday_date}"

    # Create an Elasticsearch search
    s = Search(using=es, index=index_name)
    s.aggs.bucket("rejectCode_terms", "terms", field="rejectCode.keyword", size=100)

    try:
        # Execute the search
        response = s.execute()
    except NotFoundError as e:
        return jsonify({"error": f"Index {index_name} not found"}), 404

    # Format the message with Slack blocks
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*RejectCode Stats for {yesterday_date}*"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n".join([f"{hit.key}: {hit.doc_count}" for hit in response.aggregations.rejectCode_terms.buckets])
            }
        }
    ]

    # Send the message to Slack
    payload = {"blocks": blocks}
    response = requests.post(slack_webhook_url, json=payload)

    if response.status_code == 200:
        return jsonify({"message": "Data sent to Slack successfully"})
    else:
        return jsonify({"error": f"Error sending data to Slack: {response.status_code}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
