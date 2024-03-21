#!/usr/bin/python3

import whois21
from datetime import datetime
import prometheus_client
from prometheus_client import Gauge
from flask import Response, Flask
import pytz
from decouple import config
from prometheus_client.exposition import push_to_gateway

class DomainMonitor:
    def __init__(self, domains, push_gateway_url):
        self.domains = domains.split(',')
        self.counter = Gauge('domain_check', 'Base Gauge', ['domain'])
        self.push_gateway_url = push_gateway_url

    def calculate_days_to_expiration(self):
        for domain in self.domains:
            whois = whois21.WHOIS(domain)
            expiration_date = whois.expiration_date

            if isinstance(expiration_date, list):
                expiration_date = expiration_date[0]

            print(whois.domain, expiration_date)

            if expiration_date:
                current_date = datetime.now(pytz.utc)  # Use UTC time
                days_until_expiration = (expiration_date - current_date).days
                self.counter.labels(domain=domain).set(days_until_expiration)

    def run(self):
        push_to_gateway(
            self.push_gateway_url,
            job='domain_monitoring',
            registry=prometheus_client.REGISTRY
        )

if __name__ == "__main__":
    app = Flask(__name__)
    list_domains = config('DOMAINS')
    push_gateway_url = config('PUSH_GATEWAY_URL')  # Add this line to read the Push Gateway URL from environment variables
    domain_monitor = DomainMonitor(list_domains, push_gateway_url)

    @app.route("/metrics")
    def r_value():
        domain_monitor.calculate_days_to_expiration()  # Update metrics only when the /metrics endpoint is accessed
        domain_monitor.run()  # Push metrics to the gateway
        return Response(prometheus_client.generate_latest(domain_monitor.counter), mimetype="text/plain")

    app.run(host="0.0.0.0", port=5678)
