# Agent Swarm Monitoring & Alerting

This directory contains monitoring and alerting configuration for the Agent Swarm system.

## Components

### Prometheus
- **Port:** 9090
- **Config:** `prometheus/prometheus.yml`
- **URL:** http://localhost:9090

Prometheus scrapes metrics from the application and stores them for querying.

### Grafana
- **Port:** 3000
- **Credentials:** admin/admin (change on first login)
- **URL:** http://localhost:3000

Grafana visualizes metrics with pre-configured dashboards.

### Alertmanager
- **Port:** 9093
- **Config:** `alertmanager/alertmanager.yml`
- **URL:** http://localhost:9093

Alertmanager handles alert routing and notifications.

## Quick Start

```bash
# Start monitoring stack
docker-compose up -d prometheus grafana alertmanager

# Check status
docker-compose ps

# View logs
docker-compose logs -f prometheus
docker-compose logs -f grafana
```

## Accessing Dashboards

1. Open Grafana: http://localhost:3000
2. Login with admin/admin
3. Navigate to Dashboards → Agent Swarm - Production Dashboard

## Viewing Alerts

1. Open Prometheus: http://localhost:9090
2. Navigate to Alerts tab
3. View active and firing alerts

Or visit Alertmanager: http://localhost:9093

## Metrics Endpoint

The application exposes metrics at `/metrics` endpoint for Prometheus to scrape.

Example: http://localhost:8000/metrics

## Key Metrics

- `agent_swarm_bus_publish_latency_seconds` - Bus publish latency
- `agent_swarm_decide_latency_seconds` - DECIDE processing time
- `agent_swarm_policy_eval_latency_seconds` - Policy evaluation time
- `agent_swarm_messages_published_total` - Total messages published
- `agent_swarm_active_agents` - Number of active agents
- `agent_swarm_active_tasks` - Number of active tasks
- `agent_swarm_staked_tokens` - Staked tokens by pool

## Alert Rules

View all alert rules in `alerts/alerting_rules.yml`:

- **HighBusLatency** - P99 bus latency >25ms
- **SlowDecideProcessing** - P95 DECIDE latency >2s
- **SlowPolicyEvaluation** - P95 policy eval >20ms
- **HighMessageFailureRate** - Message failures >10/sec
- **NoActiveAgents** - No agents available
- **SystemDown** - Application unreachable

## Troubleshooting

### Prometheus not scraping
- Check target in Prometheus UI: http://localhost:9090/targets
- Verify application is exposing /metrics
- Check firewall/network connectivity

### Grafana dashboard empty
- Verify Prometheus datasource is configured
- Check time range in dashboard (top right)
- Ensure metrics are being collected

### Alerts not firing
- Check alerting rules syntax in Prometheus UI
- Verify Alertmanager is connected
- Check alert evaluation interval

## Configuration

### Adding New Metrics
1. Add metric definition in `src/observability/metrics.py`
2. Record metrics in your code
3. Metrics will automatically be exported

### Adding New Alerts
1. Edit `alerts/alerting_rules.yml`
2. Add new alert rule
3. Restart Prometheus: `docker-compose restart prometheus`

### Configuring Notifications
1. Edit `alertmanager/alertmanager.yml`
2. Configure receivers (email, Slack, PagerDuty, etc.)
3. Restart Alertmanager: `docker-compose restart alertmanager`

## Production Deployment

For production:
1. Use persistent volumes for Prometheus data
2. Configure proper authentication for Grafana
3. Set up external alert receivers (Slack, PagerDuty, email)
4. Enable HTTPS for all endpoints
5. Set appropriate retention policies
6. Configure backup for dashboards and alerts
