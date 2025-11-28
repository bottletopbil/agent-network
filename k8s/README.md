# Agent Swarm Kubernetes Deployment

This directory contains Kubernetes manifests for deploying the Agent Swarm system in production.

## Prerequisites

- Kubernetes cluster (v1.24+)
- kubectl configured
- Docker for building images
- 20GB+ available storage

## Quick Start

```bash
# Deploy everything
./tools/deploy.sh deploy

# Check status  
./tools/deploy.sh status

# Access Grafana
kubectl port-forward -n agent-swarm svc/grafana 3000:3000
```

## Architecture

- **Coordinator**: 3 replicas (StatefulSet) for high availability
- **Planner Agents**: 5 replicas (Deployment)
- **Worker Agents**: 10-50 replicas (Deployment with HPA)
- **Verifier Agents**: 7 replicas (Deployment)

## Deployment Steps

### 1. Check Prerequisites
```bash
./tools/deploy.sh prereq
```

### 2. Build Images
```bash
./tools/deploy.sh build
```

### 3. Push to Registry (if using remote registry)
```bash
export DOCKER_REGISTRY=your-registry.example.com
./tools/deploy.sh push
```

### 4. Deploy
```bash
# Deploy all components
kubectl apply -f k8s/

# Or use the deployment script
./tools/deploy.sh deploy
```

### 5. Verify
```bash
# Check all pods
kubectl get pods -n agent-swarm

# Check services
kubectl get svc -n agent-swarm

# View logs
kubectl logs -f -n agent-swarm -l app=coordinator
```

## Configuration

### Environment Variables

Set in `k8s/configmaps.yaml`:
- `NATS_URL` - Message bus URL
- `REDIS_URL` - Cache URL  
- `ETCD_ENDPOINTS` - Coordination service
- `K_PLAN`, `K_RESULT` - Consensus thresholds
- `LOG_LEVEL` - Logging level

### Resource Limits

Coordinator:
- Requests: 500m CPU, 512Mi memory
- Limits: 2000m CPU, 2Gi memory

Agents:
- Requests: 250m CPU, 256Mi memory
- Limits: 1000m CPU, 1Gi memory

## Scaling

### Manual Scaling
```bash
# Scale workers
kubectl scale deployment -n agent-swarm worker-agents --replicas=20

# Scale verifiers
kubectl scale deployment -n agent-swarm verifier-agents --replicas=10
```

### Auto-Scaling

Worker agents have HPA configured:
- Min: 5 replicas
- Max: 50 replicas
- Target CPU: 70%
- Target Memory: 80%

## Monitoring

Access monitoring dashboards:

```bash
# Grafana (port 3000)
kubectl port-forward -n agent-swarm svc/grafana 3000:3000

# Prometheus (port 9090)
kubectl port-forward -n agent-swarm svc/prometheus 9090:9090
```

## Troubleshooting

### Pods not starting
```bash
# Check pod status
kubectl describe pod -n agent-swarm <pod-name>

# View logs
kubectl logs -n agent-swarm <pod-name>

# Check events
kubectl get events -n agent-swarm --sort-by='.lastTimestamp'
```

### Service unreachable
```bash
# Check service endpoints
kubectl get endpoints -n agent-swarm

# Test service connectivity
kubectl run -it --rm debug --image=busybox --restart=Never -n agent-swarm -- sh
# Inside pod:
wget -O- http://coordinator:8000/health
```

### Storage issues
```bash
# Check PVCs
kubectl get pvc -n agent-swarm

# Describe PVC
kubectl describe pvc -n agent-swarm <pvc-name>
```

## Rollback

```bash
# Rollback coordinator
kubectl rollout undo statefulset/coordinator -n agent-swarm

# Rollback agents
kubectl rollout undo deployment/worker-agents -n agent-swarm

# Or use script
./tools/deploy.sh rollback
```

## Cleanup

```bash
# Delete all resources
./tools/deploy.sh cleanup

# Or manually
kubectl delete namespace agent-swarm
```

## Production Checklist

- [ ] Configure persistent storage class
- [ ] Set up ingress for external access
- [ ] Configure TLS certificates
- [ ] Set resource quotas
- [ ] Configure network policies
- [ ] Set up log aggregation  
- [ ] Configure backup strategy
- [ ] Set up monitoring alerts
- [ ] Configure autoscaling policies
- [ ] Review security policies

## Files

- `namespace.yaml` - Namespace and RBAC
- `configmaps.yaml` - Configuration
- `services.yaml` - Service definitions
- `coordinator-statefulset.yaml` - Coordinator deployment
- `agent-deployment.yaml` - Agent deployments + HPA
- `../docker/coordinator.Dockerfile` - Coordinator image
- `../docker/agent.Dockerfile` - Agent image
- `../tools/deploy.sh` - Deployment automation
