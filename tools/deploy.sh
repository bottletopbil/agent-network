#!/bin/bash
# Agent Swarm Kubernetes Deployment Script

set -e  # Exit on error

# Colors for output
RED='\033[0:31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="agent-swarm"
DOCKER_REGISTRY="${DOCKER_REGISTRY:-localhost:5000}"
VERSION="${VERSION:-latest}"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl."
        exit 1
    fi
    
    # Check docker
    if ! command -v docker &> /dev/null; then
        log_error "docker not found. Please install docker."
        exit 1
    fi
    
    # Check kubernetes connection
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster."
        exit 1
    fi
    
    log_info "Prerequisites check passed."
}

build_images() {
    log_info "Building Docker images..."
    
    # Build coordinator
    log_info "Building coordinator image..."
    docker build -f docker/coordinator.Dockerfile -t ${DOCKER_REGISTRY}/agent-swarm/coordinator:${VERSION} .
    
    # Build agent
    log_info "Building agent image..."
    docker build -f docker/agent.Dockerfile -t ${DOCKER_REGISTRY}/agent-swarm/agent:${VERSION} .
    
    log_info "Docker images built successfully."
}

push_images() {
    log_info "Pushing images to registry..."
    
    docker push ${DOCKER_REGISTRY}/agent-swarm/coordinator:${VERSION}
    docker push ${DOCKER_REGISTRY}/agent-swarm/agent:${VERSION}
    
    log_info "Images pushed successfully."
}

create_namespace() {
    log_info "Creating namespace..."
    
    if kubectl get namespace ${NAMESPACE} &> /dev/null; then
        log_warn "Namespace ${NAMESPACE} already exists."
    else
        kubectl apply -f k8s/namespace.yaml
        log_info "Namespace created."
    fi
}

deploy_infrastructure() {
    log_info "Deploying infrastructure components..."
    
    # ConfigMaps
    kubectl apply -f k8s/configmaps.yaml
    
    # Services
    kubectl apply -f k8s/services.yaml
    
    log_info "Infrastructure deployed."
}

deploy_application() {
    log_info "Deploying application components..."
    
    # Coordinator StatefulSet
    kubectl apply -f k8s/coordinator-statefulset.yaml
    
    # Agent Deployments
    kubectl apply -f k8s/agent-deployment.yaml
    
    log_info "Application deployed."
}

wait_for_deployment() {
    log_info "Waiting for deployments to be ready..."
    
    # Wait for coordinator
    kubectl wait --for=condition=ready pod \
        -l app=coordinator \
        -n ${NAMESPACE} \
        --timeout=300s || log_warn "Coordinator pods not ready yet"
    
    # Wait for agents
    kubectl wait --for=condition=ready pod \
        -l app=agent \
        -n ${NAMESPACE} \
        --timeout=300s || log_warn "Agent pods not ready yet"
    
    log_info "Deployment complete."
}

show_status() {
    log_info "Deployment status:"
    echo ""
    kubectl get all -n ${NAMESPACE}
    echo ""
    
    log_info "To view logs:"
    echo "  kubectl logs -f -n ${NAMESPACE} -l app=coordinator"
    echo "  kubectl logs -f -n ${NAMESPACE} -l app=agent,agent-type=planner"
    echo ""
    
    log_info "To access Grafana:"
    echo "  kubectl port-forward -n ${NAMESPACE} svc/grafana 3000:3000"
    echo "  Open: http://localhost:3000 (admin/admin)"
}

rollback() {
    log_error "Deployment failed. Rolling back..."
    
    kubectl rollout undo statefulset/coordinator -n ${NAMESPACE} || true
    kubectl rollout undo deployment/planner-agents -n ${NAMESPACE} || true
    kubectl rollout undo deployment/worker-agents -n ${NAMESPACE} || true
    kubectl rollout undo deployment/verifier-agents -n ${NAMESPACE} || true
    
    log_info "Rollback complete."
}

cleanup() {
    log_warn "Cleaning up deployment..."
    
    kubectl delete -f k8s/agent-deployment.yaml --ignore-not-found=true
    kubectl delete -f k8s/coordinator-statefulset.yaml --ignore-not-found=true
    kubectl delete -f k8s/services.yaml --ignore-not-found=true
    kubectl delete -f k8s/configmaps.yaml --ignore-not-found=true
    kubectl delete -f k8s/namespace.yaml --ignore-not-found=true
    
    log_info "Cleanup complete."
}

# Main script
main() {
    case "${1:-deploy}" in
        prereq)
            check_prerequisites
            ;;
        build)
            check_prerequisites
            build_images
            ;;
        push)
            push_images
            ;;
        deploy)
            log_info "Starting deployment..."
            check_prerequisites
            build_images
            create_namespace
            deploy_infrastructure
            deploy_application
            wait_for_deployment
            show_status
            log_info "Deployment successful!"
            ;;
        status)
            show_status
            ;;
        rollback)
            rollback
            ;;
        cleanup)
            cleanup
            ;;
        *)
            echo "Usage: $0 {prereq|build|push|deploy|status|rollback|cleanup}"
            echo ""
            echo "Commands:"
            echo "  prereq   - Check prerequisites"
            echo "  build    - Build Docker images"
            echo "  push     - Push images to registry"
            echo "  deploy   - Full deployment (build + deploy)"
            echo "  status   - Show deployment status"
            echo "  rollback - Rollback last deployment"
            echo "  cleanup  - Remove all resources"
            echo ""
            echo "Environment variables:"
            echo "  DOCKER_REGISTRY - Docker registry URL (default: localhost:5000)"
            echo "  VERSION         - Image version tag (default: latest)"
            exit 1
            ;;
    esac
}

# Trap errors and rollback
trap 'log_error "An error occurred. Check logs above."' ERR

main "$@"
