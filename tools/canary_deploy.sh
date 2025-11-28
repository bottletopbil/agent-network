#!/bin/bash
# Canary Deployment Script for Agent Swarm

set -e

# Configuration
NAMESPACE="${NAMESPACE:-agent-swarm}"
CANARY_PERCENTAGE="${CANARY_PERCENTAGE:-10}"
CANARY_TAG="${CANARY_TAG:-canary}"
MONITOR_DURATION="${MONITOR_DURATION:-300}"  # 5 minutes
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-30}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

calculate_canary_replicas() {
    local deployment=$1
    local total=$(kubectl get deployment $deployment -n $NAMESPACE -o jsonpath='{.spec.replicas}')
    local canary=$(( total * CANARY_PERCENTAGE / 100 ))
    
    # Ensure at least 1 canary pod
    if [ $canary -eq 0 ]; then
        canary=1
    fi
    
    echo $canary
}

create_canary() {
    log_info "Creating canary deployments..."
    
    # Create canary for each deployment
    for deployment in planner-agents worker-agents verifier-agents; do
        log_info "Creating canary for $deployment..."
        
        # Get canary replica count
        canary_replicas=$(calculate_canary_replicas $deployment)
        
        # Export existing deployment and modify for canary
        kubectl get deployment $deployment -n $NAMESPACE -o yaml | \
        sed "s/name: $deployment/name: $deployment-canary/" | \
        sed "s/replicas: .*/replicas: $canary_replicas/" | \
        sed "/labels:/a\\      version: canary" | \
        sed "s|image: .*|image: ghcr.io/\$IMAGE_NAME/agent:${CANARY_TAG}|" | \
        kubectl apply -f -
        
        log_info "Canary for $deployment created with $canary_replicas replicas"
    done
    
    # Create canary for coordinator (1 pod out of 3)
    log_info "Creating canary for coordinator..."
    kubectl get statefulset coordinator -n $NAMESPACE -o yaml | \
    sed "s/name: coordinator/name: coordinator-canary/" | \
    sed "s/replicas: .*/replicas: 1/" | \
    sed "/labels:/a\\      version: canary" | \
    sed "s|image: .*|image: ghcr.io/\$IMAGE_NAME/coordinator:${CANARY_TAG}|" | \
    kubectl apply -f -
    
    log_info "Canary deployments created!"
    log_info "Waiting for canary pods to be ready..."
    
    kubectl wait --for=condition=ready pod \
        -l version=canary \
        -n $NAMESPACE \
        --timeout=300s || {
        log_error "Canary pods failed to become ready!"
        return 1
    }
    
    log_info "Canary pods are ready!"
}

monitor_canary() {
    log_info "Monitoring canary health for ${MONITOR_DURATION}s..."
    
    local start_time=$(date +%s)
    local end_time=$((start_time + MONITOR_DURATION))
    local errors=0
    local max_errors=5
    
    while [ $(date +%s) -lt $end_time ]; do
        log_debug "Checking canary health..."
        
        # Check pod status
        local unhealthy=$(kubectl get pods -l version=canary -n $NAMESPACE | grep -v Running | grep -v Completed | wc -l)
        if [ $unhealthy -gt 1 ]; then
            log_warn "Found $((unhealthy - 1)) unhealthy canary pods"
            errors=$((errors + 1))
        else
            log_debug "All canary pods healthy"
        fi
        
        # Check error rate from Prometheus
        # This would query actual metrics in production
        # For now, simulate by checking pod restarts
        local restarts=$(kubectl get pods -l version=canary -n $NAMESPACE -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}' | awk '{for(i=1;i<=NF;i++) sum+=$i; print sum}')
        if [ -n "$restarts" ] && [ $restarts -gt 0 ]; then
            log_warn "Canary pods have restarted $restarts times"
            errors=$((errors + 1))
        fi
        
        # Check if too many errors
        if [ $errors -ge $max_errors ]; then
            log_error "Too many errors detected during canary monitoring!"
            log_error "Error count: $errors / $max_errors"
            return 1
        fi
        
        # Show progress
        local elapsed=$(($(date +%s) - start_time))
        local remaining=$((MONITOR_DURATION - elapsed))
        log_debug "Monitoring... ${elapsed}s elapsed, ${remaining}s remaining (errors: $errors)"
        
        sleep $HEALTH_CHECK_INTERVAL
    done
    
    log_info "Canary monitoring complete!"
    log_info "Total errors: $errors / $max_errors"
    
    if [ $errors -eq 0 ]; then
        log_info "✓ Canary is healthy! Safe to promote."
    else
        log_warn "⚠ Canary had some issues but within threshold."
    fi
    
    return 0
}

promote_canary() {
    log_info "Promoting canary to production..."
    
    # Update all deployments to canary version
    for deployment in planner-agents worker-agents verifier-agents; do
        log_info "Updating $deployment to canary version..."
        
        kubectl set image deployment/$deployment -n $NAMESPACE \
            $(kubectl get deployment $deployment -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].name}')=ghcr.io/$IMAGE_NAME/agent:${CANARY_TAG}
        
        kubectl rollout status deployment/$deployment -n $NAMESPACE --timeout=300s || {
            log_error "Failed to update $deployment!"
            return 1
        }
    done
    
    # Update coordinator
    log_info "Updating coordinator to canary version..."
    kubectl set image statefulset/coordinator -n $NAMESPACE \
        coordinator=ghcr.io/$IMAGE_NAME/coordinator:${CANARY_TAG}
    
    kubectl rollout status statefulset/coordinator -n $NAMESPACE --timeout=300s || {
        log_error "Failed to update coordinator!"
        return 1
    }
    
    log_info "All components promoted to canary version!"
}

cleanup_canary() {
    log_info "Cleaning up canary resources..."
    
    kubectl delete deployment planner-agents-canary -n $NAMESPACE --ignore-not-found=true
    kubectl delete deployment worker-agents-canary -n $NAMESPACE --ignore-not-found=true
    kubectl delete deployment verifier-agents-canary -n $NAMESPACE --ignore-not-found=true
    kubectl delete statefulset coordinator-canary -n $NAMESPACE --ignore-not-found=true
    
    log_info "Canary resources cleaned up!"
}

show_status() {
    log_info "Canary Deployment Status:"
    echo ""
    
    echo "Production pods:"
    kubectl get pods -l app=coordinator,version!=canary -n $NAMESPACE 2>/dev/null || echo "  None"
    kubectl get pods -l app=agent,version!=canary -n $NAMESPACE 2>/dev/null || echo "  None"
    
    echo ""
    echo "Canary pods:"
    kubectl get pods -l version=canary -n $NAMESPACE 2>/dev/null || echo "  None"
    
    echo ""
    log_info "Image versions:"
    kubectl get deployments,statefulsets -n $NAMESPACE -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}'
}

main() {
    case "${1:-help}" in
        create)
            create_canary
            ;;
        monitor)
            monitor_canary
            ;;
        promote)
            promote_canary
            ;;
        cleanup)
            cleanup_canary
            ;;
        status)
            show_status
            ;;
        full)
            create_canary && \
            monitor_canary && \
            promote_canary && \
            cleanup_canary
            ;;
        *)
            echo "Usage: $0 {create|monitor|promote|cleanup|status|full}"
            echo ""
            echo "Commands:"
            echo "  create   - Create canary deployments (${CANARY_PERCENTAGE}% of traffic)"
            echo "  monitor  - Monitor canary health for ${MONITOR_DURATION}s"
            echo "  promote  - Promote canary to production"
            echo "  cleanup  - Remove canary resources"
            echo "  status   - Show current canary status"
            echo "  full     - Run complete canary deployment"
            echo ""
            echo "Environment variables:"
            echo "  NAMESPACE              - Kubernetes namespace (default: agent-swarm)"
            echo "  CANARY_PERCENTAGE      - % of traffic to canary (default: 10)"
            echo "  CANARY_TAG             - Image tag for canary (default: canary)"
            echo "  MONITOR_DURATION       - Monitoring duration in seconds (default: 300)"
            echo "  HEALTH_CHECK_INTERVAL  - Health check interval in seconds (default: 30)"
            exit 1
            ;;
    esac
}

main "$@"
