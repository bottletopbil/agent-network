# CI/CD Pipeline for Agent Swarm

This directory contains GitHub Actions workflows for automated testing, building, and deployment.

## Overview

The CI/CD pipeline consists of two main workflows:
- **CI (Continuous Integration)**: Lint, test, and build on every PR/push
- **CD (Continuous Deployment)**: Deploy to staging and production with canary releases

## Workflows

### 1. Continuous Integration (`ci.yml`)

Triggered on:
- Pull requests to `main` or `develop`
- Pushes to `main` or `develop`

**Jobs:**
1. **Lint** - Code quality checks
   - Black (code formatting)
   - Flake8 (linting)
   - MyPy (type checking)

2. **Test** - Unit tests across Python versions
   - Matrix: Python 3.9, 3.10, 3.11
   - Services: Redis, NATS
   - Coverage reporting to Codecov

3. **Security** - Security scanning
   - Safety (dependency vulnerabilities)
   - Bandit (security issues in code)

4. **Build** - Docker image building
   - Coordinator image
   - Agent image
   - Push to GitHub Container Registry
   - Layer caching for faster builds

5. **Integration Test** - End-to-end tests
   - Docker Compose environment
   - Integration test suite

### 2. Continuous Deployment (`deploy.yml`)

Triggered when CI workflow completes successfully on `main` branch.

**Deployment Flow:**
```
CI Success → Staging → Canary (10%) → Monitor → Production → Cleanup
                ↓          ↓             ↓           ↓
            Smoke Test  Health Check  Promote   Verify Health
```

**Jobs:**
1. **Deploy to Staging**
   - Deploy to staging environment
   - Run smoke tests
   - Verify basic functionality

2. **Canary Deploy to Production**
   - Deploy 10% canary pods
   - Monitor for 5 minutes
   - Auto-rollback on health check failure

3. **Promote to Production**
   - Manual approval required (GitHub environment)
   - Full rollout to production
   - Health verification
   - Auto-rollback on failure

4. **Rollback on Failure**
   - Automatic rollback if any step fails
   - Notification of failure

## Deployment Scripts

### canary_deploy.sh

Manages canary deployments:

```bash
# Create canary (10% of replicas)
./tools/canary_deploy.sh create

# Monitor canary health
./tools/canary_deploy.sh monitor

# Promote canary to production
./tools/canary_deploy.sh promote

# Cleanup canary resources
./tools/canary_deploy.sh cleanup

# Full canary deployment
./tools/canary_deploy.sh full
```

**Features:**
- Automatic replica calculation (10% of production)
- Health monitoring for 5 minutes
- Error threshold detection
- Safe promotion process

### rollback.sh

Handles rollbacks:

```bash
# Rollback canary
./tools/rollback.sh canary

# Rollback production to previous version
./tools/rollback.sh production

# Rollback to specific revision
./tools/rollback.sh revision 3

# View deployment history
./tools/rollback.sh history

# Pause ongoing rollouts
./tools/rollback.sh pause
```

**Features:**
- Automatic rollback on failure
- Revision-specific rollback
- Health verification
- Rollout pause/resume

## Setup

### Required Secrets

Configure in GitHub repository settings:

```
KUBECONFIG_STAGING      - Base64-encoded kubeconfig for staging
KUBECONFIG_PRODUCTION   - Base64-encoded kubeconfig for production
GITHUB_TOKEN            - Auto-provided by GitHub Actions
```

To create kubeconfig secret:
```bash
cat ~/.kube/config | base64
```

### GitHub Environments

Create environments in repository settings:
- `staging` - Auto-deploy on CI success
- `production-canary` - Canary deployment
- `production` - Full production (requires approval)

### Registry Authentication

The workflows use GitHub Container Registry (ghcr.io):
- Authentication via `GITHUB_TOKEN`
- Images: `ghcr.io/<owner>/<repo>/coordinator:tag`
- Images: `ghcr.io/<owner>/<repo>/agent:tag`

## Canary Deployment Strategy

**Phase 1: Create Canary (10% traffic)**
- 1 coordinator pod (out of 3)
- 10% of agent pods
- Separate canary  deployments

**Phase 2: Monitor (5 minutes)**
- Check pod health every 30s
- Monitor restart counts
- Track error rates (via Prometheus in production)
- Auto-rollback if >5 errors

**Phase 3: Promote**
- Update production deployments to canary version
- Gradual rollout with health checks
- Cleanup canary resources

**Phase 4: Verify**
- Full health check
- Metrics verification
- Auto-rollback on failure

## Health Checks

### During Deployment
- Pod readiness probes
- HTTP endpoint checks (/health)
- Metrics endpoint (/metrics)
- Pod restart monitoring

### Production Monitoring
- Prometheus metrics
- Error rate thresholds
- Latency percentiles
- Resource utilization

## Rollback Triggers

Automatic rollback occurs if:
- Canary pods fail to start
- Health checks fail
- Error threshold exceeded
- Resource exhaustion
- Timeout exceeded

## Usage

### Normal Deployment
```bash
# Make changes
git add .
git commit -m "feat: new feature"
git push origin main

# CI runs automatically
# CD deploys to staging
# Canary deployed to production (10%)
# Manual approval for full rollout
```

### Emergency Rollback
```bash
# From local machine
./tools/rollback.sh production

# Or trigger via GitHub Actions
# Go to Actions → Continuous Deployment → Re-run failed jobs
```

### Manual Canary
```bash
# Deploy canary manually
export CANARY_TAG=v1.2.3
./tools/canary_deploy.sh create

# Monitor
./tools/canary_deploy.sh monitor

# Promote if healthy
./tools/canary_deploy.sh promote
```

## Monitoring Deployment

```bash
# Watch deployment progress
kubectl get pods -n agent-swarm -w

# Check rollout status
kubectl rollout status deployment/worker-agents -n agent-swarm

# View deployment history
./tools/rollback.sh history

# Check canary status
./tools/canary_deploy.sh status
```

## Best Practices

1. **Always test locally first**
   ```bash
   pytest tests/ -v
   ./tools/deploy.sh build
   ```

2. **Use feature branches**
   - Create PR for review
   - CI runs on PR
   - Merge to main triggers deployment

3. **Monitor deployments**
   - Watch Grafana dashboards
   - Check Prometheus alerts
   - Review logs

4. **Quick rollback**
   - Keep rollback script ready
   - Know your revision numbers
   - Test rollback process

5. **Canary duration**
   - Default: 5 minutes
   - Adjust based on traffic patterns
   - Longer for major changes

## Troubleshooting

### CI Failing
```bash
# Check workflow logs in GitHub Actions
# Run tests locally
pytest tests/ -v

# Fix issues and push
git commit --amend
git push --force
```

### Deployment Stuck
```bash
# Check pod status
kubectl get pods -n agent-swarm

# View events
kubectl get events -n agent-swarm --sort-by='.lastTimestamp'

# Rollback if needed
./tools/rollback.sh production
```

### Canary Issues
```bash
# View canary logs
kubectl logs -l version=canary -n agent-swarm

# Delete canary and retry
./tools/canary_deploy.sh cleanup
./tools/canary_deploy.sh create
```

## Performance

- **CI Duration**: ~15-20 minutes
- **Build Duration**: ~5-10 minutes (with cache)
- **Staging Deploy**: ~5 minutes
- **Canary Deploy**: ~5 minutes
- **Canary Monitor**: 5 minutes (configurable)
- **Full Rollout**: ~10 minutes
- **Total**: ~40-50 minutes from push to production

## Cost Optimization

- **Layer Caching**: Reduces build time by 60%
- **Matrix Testing**: Parallel execution
- **Docker Buildx**: Multi-platform builds
- **GitHub Actions**: Free for public repos
- **Self-hosted Runners**: Option for private repos
