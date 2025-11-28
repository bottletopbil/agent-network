#!/bin/bash
# Rollback Script for Agent Swarm

set -e

# Configuration
NAMESPACE="${NAMESPACE:-agent-swarm}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

rollback_deployment() {
    local deployment=$1
    
    log_info "Rolling back $deployment..."
    
    kubectl rollout undo deployment/$deployment -n $NAMESPACE || {
        log_error "Failed to rollback $deployment"
        return 1
    }
    
    kubectl rollout status deployment/$deployment -n $NAMESPACE --timeout=300s || {
        log_error "Rollback of $deployment did not complete successfully"
        return 1
    }
    
    log_info "✓ $deployment rolled back successfully"
}

rollback_statefulset() {
    local statefulset=$1
    
    log_info "Rolling back $statefulset..."
    
    kubectl rollout undo statefulset/$statefulset -n $NAMESPACE || {
        log_error "Failed to rollback $statefulset"
        return 1
    }
    
    kubectl rollout status statefulset/$statefulset -n $NAMESPACE --timeout=300s || {
        log_error "Rollback of $statefulset did not complete successfully"
        return 1
    }
    
    log_info "✓ $statefulset rolled back successfully"
}

rollback_canary() {
    log_info "Rolling back canary deployment..."
    
    # Delete canary resources
    kubectl delete deployment planner-agents-canary -n $NAMESPACE --ignore-not-found=true
    kubectl delete deployment worker-agents-canary -n $NAMESPACE --ignore-not-found=true
    kubectl delete deployment verifier-agents-canary -n $NAMESPACE --ignore-not-found=true
    kubectl delete statefulset coordinator-canary -n $NAMESPACE --ignore-not-found=true
    
    log_info "Canary resources removed"
}

rollback_production() {
    log_info "Rolling back production deployment..."
    log_warn "This will revert all components to their previous version!"
    
    # Rollback all deployments
    rollback_deployment "planner-agents"
    rollback_deployment "worker-agents"
    rollback_deployment "verifier-agents"
    
    # Rollback statefulset
    rollback_statefulset "coordinator"
    
    log_info "Production rollback complete!"
}

rollback_to_revision() {
    local revision=$1
    
    if [ -z "$revision" ]; then
        log_error "No revision specified!"
        exit 1
    fi
    
    log_info "Rolling back to revision $revision..."
    
    # Rollback deployments to specific revision
    for deployment in planner-agents worker-agents verifier-agents; do
        log_info "Rolling back $deployment to revision $revision..."
        
        kubectl rollout undo deployment/$deployment -n $NAMESPACE --to-revision=$revision || {
            log_error "Failed to rollback $deployment to revision $revision"
            return 1
        }
        
        kubectl rollout status deployment/$deployment -n $NAMESPACE --timeout=300s
    done
    
    # Rollback coordinator
    log_info "Rolling back coordinator to revision $revision..."
    kubectl rollout undo statefulset/coordinator -n $NAMESPACE --to-revision=$revision || {
        log_error "Failed to rollback coordinator to revision $revision"
        return 1
    }
    
    kubectl rollout status statefulset/coordinator -n $NAMESPACE --timeout=300s
    
    log_info "Rollback to revision $revision complete!"
}

show_history() {
    log_info "Deployment History:"
    echo ""
    
    echo "=== Coordinator ==="
    kubectl rollout history statefulset/coordinator -n $NAMESPACE
    
    echo ""
    echo "=== Planner Agents ==="
    kubectl rollout history deployment/planner-agents -n $NAMESPACE
    
    echo ""
    echo "=== Worker Agents ==="
    kubectl rollout history deployment/worker-agents -n $NAMESPACE
    
    echo ""
    echo "=== Verifier Agents ==="
    kubectl rollout history deployment/verifier-agents -n $NAMESPACE
}

verify_rollback() {
    log_info "Verifying rollback..."
    
    # Check all pods are running
    local unhealthy=$(kubectl get pods -n $NAMESPACE | grep -v Running | grep -v Completed | wc -l)
    
    if [ $unhealthy -gt 1 ]; then
        log_error "Found $((unhealthy - 1)) unhealthy pods after rollback!"
        kubectl get pods -n $NAMESPACE
        return 1
    fi
    
    # Check coordinator health
    kubectl run curl-test --image=curlimages/curl:latest --rm -it --restart=Never -n $NAMESPACE -- \
        curl -f http://coordinator:8000/health || {
        log_error "Coordinator health check failed after rollback!"
        return 1
    }
    
    log_info "✓ Rollback verified successfully!"
}

pause_rollout() {
    log_warn "Pausing all rollouts..."
    
    kubectl rollout pause deployment/planner-agents -n $NAMESPACE
    kubectl rollout pause deployment/worker-agents -n $NAMESPACE
    kubectl rollout pause deployment/verifier-agents -n $NAMESPACE
    kubectl rollout pause statefulset/coordinator -n $NAMESPACE
    
    log_info "All rollouts paused"
}

resume_rollout() {
    log_info "Resuming all rollouts..."
    
    kubectl rollout resume deployment/planner-agents -n $NAMESPACE
    kubectl rollout resume deployment/worker-agents -n $NAMESPACE
    kubectl rollout resume deployment/verifier-agents -n $NAMESPACE
    kubectl rollout resume statefulset/coordinator -n $NAMESPACE
    
    log_info "All rollouts resumed"
}

main() {
    case "${1:-help}" in
        canary)
            rollback_canary
            ;;
        production)
            rollback_production
            verify_rollback
            ;;
        revision)
            rollback_to_revision "$2"
            verify_rollback
            ;;
        history)
            show_history
            ;;
        verify)
            verify_rollback
            ;;
        pause)
            pause_rollout
            ;;
        resume)
            resume_rollout
            ;;
        *)
            echo "Usage: $0 {canary|production|revision <N>|history|verify|pause|resume}"
            echo ""
            echo "Commands:"
            echo "  canary          - Rollback canary deployment"
            echo "  production      - Rollback production to previous version"
            echo "  revision <N>    - Rollback to specific revision number"
            echo "  history         - Show deployment history"
            echo "  verify          - Verify rollback was successful"
            echo "  pause           - Pause all ongoing rollouts"
            echo "  resume          - Resume paused rollouts"
            echo ""
            echo "Environment variables:"
            echo "  NAMESPACE       - Kubernetes namespace (default: agent-swarm)"
            echo ""
            echo "Examples:"
            echo "  $0 production              # Rollback to previous version"
            echo "  $0 revision 3              # Rollback to revision 3"
            echo "  $0 history                 # View available revisions"
            exit 1
            ;;
    esac
}

main "$@"
