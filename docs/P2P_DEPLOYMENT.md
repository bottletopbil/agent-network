# P2P Deployment Guide

This guide covers deploying CAN Swarm nodes in full P2P mode using libp2p for peer-to-peer communication.

## Overview

The P2P transport layer uses libp2p with Gossipsub for message propagation, replacing or augmenting NATS as the message bus. This enables:

- **Decentralized Operation**: No central message broker required
- **NAT Traversal**: Automatic connection through firewalls using circuit relays
- **Peer Discovery**: Automatic peer finding via mDNS (local) and DHT (distributed)
- **Mesh Topology**: Direct peer-to-peer connections with gossip-based propagation

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Enable P2P transport
P2P_ENABLED=true

# Use P2P as primary transport (true) or fallback (false)
P2P_PRIMARY=true

# Enable NATS as fallback when P2P is primary
NATS_FALLBACK=true

# P2P Node Listen Address
P2P_LISTEN_ADDR=/ip4/0.0.0.0/tcp/4001

# P2P Bootstrap Nodes (comma-separated multiaddrs)
P2P_BOOTSTRAP_NODES=/ip4/1.2.3.4/tcp/4001/p2p/QmBootstrap1,/ip4/5.6.7.8/tcp/4001/p2p/QmBootstrap2

# Enable mDNS for local peer discovery
P2P_MDNS_ENABLED=true

# Enable DHT for distributed peer discovery
P2P_DHT_ENABLED=true

# Connection Pool Settings
P2P_MAX_CONNECTIONS=100
P2P_CONNECTION_TIMEOUT=30

# Circuit Relay for NAT Traversal
P2P_CIRCUIT_RELAY_ENABLED=true
```

### Operating Modes

#### Mode 1: P2P Only
```bash
P2P_ENABLED=true
P2P_PRIMARY=true
NATS_FALLBACK=false
```

Pure P2P mode. No NATS dependency. Best for fully decentralized deployments.

#### Mode 2: P2P Primary with NATS Fallback
```bash
P2P_ENABLED=true
P2P_PRIMARY=true
NATS_FALLBACK=true
```

Hybrid mode. Prefers P2P but falls back to NATS if P2P fails. Best for migration phase.

#### Mode 3: NATS Primary with P2P Fallback
```bash
P2P_ENABLED=true
P2P_PRIMARY=false
```

Uses NATS as primary transport, P2P for redundancy. Best for gradual rollout.

## Network Configuration

### Firewall Requirements

#### Required Ports

- **TCP 4001**: libp2p node communication (default, configurable)
- **UDP 4001**: QUIC transport (optional, for better NAT traversal)

#### Firewall Rules

**For public-facing nodes (bootstrap nodes):**
```bash
# Allow inbound P2P connections
sudo ufw allow 4001/tcp
sudo ufw allow 4001/udp
```

**For internal nodes (behind NAT):**
```bash
# Allow outbound connections (usually allowed by default)
# No inbound rules needed if using circuit relay
```

### NAT Traversal

CAN Swarm supports multiple NAT traversal techniques:

#### 1. Circuit Relay

Automatically enabled by default. Nodes behind NAT can communicate through relay nodes.

**How it works:**
1. Node A (behind NAT) connects outbound to Relay Node R
2. Node B (behind NAT) connects outbound to Relay Node R
3. A and B can communicate through R

**Configuration:**
```bash
P2P_CIRCUIT_RELAY_ENABLED=true
```

**Designate a node as a relay:**
```python
from src.p2p.circuit_relay import CircuitRelayServer

relay = CircuitRelayServer(p2p_node)
await relay.start()
```

#### 2. Hole Punching

Automatic UDP hole punching for direct connections (requires QUIC transport).

**Configuration:**
```bash
P2P_LISTEN_ADDR=/ip4/0.0.0.0/tcp/4001,/ip4/0.0.0.0/udp/4001/quic
```

#### 3. UPnP

Automatic port forwarding on compatible routers.

> ⚠️ **Note**: UPnP is not currently implemented. Use circuit relay instead.

### Public IP Detection

libp2p automatically detects your public IP through:
- STUN-like identify protocol
- Observation from connected peers
- Manual configuration (if needed)

**Manual public IP:**
```bash
P2P_ANNOUNCE_ADDRS=/ip4/203.0.113.42/tcp/4001
```

## Bootstrap Node Configuration

Bootstrap nodes help new nodes discover the network.

### Running a Bootstrap Node

**Requirements:**
- Public IP or port forwarding
- High availability (24/7 uptime recommended)
- Good bandwidth (1 Mbps+ recommended)

**Configuration:**

1. **Set static listen address:**
   ```bash
   P2P_LISTEN_ADDR=/ip4/0.0.0.0/tcp/4001
   ```

2. **Enable DHT server mode:**
   ```python
   from src.p2p.node import P2PNode
   
   node = P2PNode(
       listen_addr="/ip4/0.0.0.0/tcp/4001",
       dht_server_mode=True
   )
   ```

3. **Get your peer ID:**
   ```bash
   python -c "from src.p2p.node import P2PNode; import asyncio; node = P2PNode(); asyncio.run(node.start()); print(node.get_peer_id())"
   ```

4. **Share your multiaddr:**
   ```
   /ip4/YOUR_PUBLIC_IP/tcp/4001/p2p/YOUR_PEER_ID
   ```

### Public Bootstrap Nodes

CAN Swarm provides public bootstrap nodes:

```
/ip4/bootstrap1.canswarm.network/tcp/4001/p2p/QmBootstrap1
/ip4/bootstrap2.canswarm.network/tcp/4001/p2p/QmBootstrap2
/ip4/bootstrap3.canswarm.network/tcp/4001/p2p/QmBootstrap3
```

> 🚧 **Note**: Public bootstrap nodes are not yet deployed. For now, run your own.

## Peer Discovery

### mDNS (Local Discovery)

Automatically discovers peers on the same local network (LAN).

**Use cases:**
- Development environments
- Local testing
- Private networks

**Configuration:**
```bash
P2P_MDNS_ENABLED=true
```

**How it works:**
1. Node broadcasts presence via mDNS (`_swarm._tcp.local`)
2. Other nodes on LAN respond
3. Bidirectional connections established automatically

### DHT (Distributed Discovery)

Discovers peers across the internet using a distributed hash table.

**Use cases:**
- Production deployments
- Cross-region networks
- Public networks

**Configuration:**
```bash
P2P_DHT_ENABLED=true
P2P_BOOTSTRAP_NODES=/ip4/1.2.3.4/tcp/4001/p2p/QmBootstrap1
```

**How it works:**
1. Node connects to bootstrap nodes
2. Node announces itself in DHT
3. Other nodes query DHT to find peers
4. Connections established based on routing needs

## Connection Management

### Connection Limits

Control resource usage with connection limits:

```bash
# Maximum concurrent connections
P2P_MAX_CONNECTIONS=100

# Connection timeout (seconds)
P2P_CONNECTION_TIMEOUT=30
```

### Peer Reputation

Nodes track peer quality and prioritize reliable peers:

```python
from src.p2p.peer_reputation import PeerReputation

reputation = PeerReputation(
    latency_weight=0.3,
    reliability_weight=0.5,
    history_weight=0.2
)

# Automatically blacklists peers with score < 0.3
```

### Connection Pool Behavior

- Maintains target number of connections
- Rotates out low-quality peers
- Prefers high-reputation peers
- Automatically reconnects on disconnect

## Deployment Scenarios

### Scenario 1: Single-Region Development

**Topology:** Full mesh via mDNS  
**Nodes:** 3-10  
**Config:**

```bash
P2P_ENABLED=true
P2P_PRIMARY=true
NATS_FALLBACK=false
P2P_MDNS_ENABLED=true
P2P_DHT_ENABLED=false
```

**Deployment:**
```bash
# Node 1
python -m src.main

# Node 2
python -m src.main

# Nodes discover each other automatically via mDNS
```

### Scenario 2: Multi-Region Production

**Topology:** DHT-based discovery with bootstrap nodes  
**Nodes:** 10-100+  
**Config:**

```bash
P2P_ENABLED=true
P2P_PRIMARY=true
NATS_FALLBACK=true
P2P_MDNS_ENABLED=false
P2P_DHT_ENABLED=true
P2P_BOOTSTRAP_NODES=/dns4/bootstrap1.example.com/tcp/4001/p2p/QmBootstrap1
```

**Deployment:**

1. **Deploy bootstrap nodes first:**
   ```bash
   # On bootstrap1.example.com
   P2P_LISTEN_ADDR=/ip4/0.0.0.0/tcp/4001 python -m src.main --bootstrap
   ```

2. **Deploy worker nodes:**
   ```bash
   # On each worker
   P2P_BOOTSTRAP_NODES=/dns4/bootstrap1.example.com/tcp/4001/p2p/QmBootstrap1 python -m src.main
   ```

### Scenario 3: Behind Corporate Firewall

**Topology:** Circuit relay through public relay node  
**Nodes:** Internal nodes behind NAT  
**Config:**

```bash
P2P_ENABLED=true
P2P_PRIMARY=true
P2P_CIRCUIT_RELAY_ENABLED=true
P2P_BOOTSTRAP_NODES=/ip4/relay.example.com/tcp/4001/p2p/QmRelay1
```

**Deployment:**

1. **Deploy public relay node (outside firewall):**
   ```python
   from src.p2p.circuit_relay import CircuitRelayServer
   
   relay = CircuitRelayServer(node, max_circuits=100)
   await relay.start()
   ```

2. **Internal nodes connect through relay:**
   ```bash
   # Automatic - no special config needed
   # Nodes will use relay for NAT traversal
   ```

## Monitoring & Troubleshooting

### Connection Status

Check node connectivity:

```python
from src.p2p.node import P2PNode

node = P2PNode()
await node.start()

# Get connected peers
peers = node.get_connected_peers()
print(f"Connected to {len(peers)} peers")

# Get multiaddrs
addrs = node.get_multiaddrs()
print(f"Listening on: {addrs}")
```

### Metrics

Key metrics to monitor:

- **Connected Peers**: Should be > 3 for redundancy
- **Message Latency**: P99 should be < 100ms in same region
- **Propagation Rate**: Should be > 95% for critical messages
- **Connection Churn**: Low is better (stable mesh)

Access metrics:

```python
from src.bus import get_bus

bus = get_bus()
stats = bus.get_stats()
print(f"Mesh stats: {stats}")
```

### Common Issues

#### Issue: No peers connecting

**Symptoms:**
- `get_connected_peers()` returns empty list
- Messages not propagating

**Solutions:**
1. Check firewall allows outbound connections
2. Verify bootstrap nodes are reachable
3. Check P2P_BOOTSTRAP_NODES format
4. Enable verbose logging: `LOG_LEVEL=DEBUG`

#### Issue: High message latency

**Symptoms:**
- P99 latency > 500ms
- Slow DECIDE confirmations

**Solutions:**
1. Check network bandwidth
2. Reduce P2P_MAX_CONNECTIONS (less overhead)
3. Enable regional bootstrap nodes
4. Check peer reputation scores

#### Issue: Messages not reaching all peers

**Symptoms:**
- Propagation rate < 90%
- Some nodes miss messages

**Solutions:**
1. Increase gossipsub mesh degree (in gossipsub.py)
2. Check for network partitions
3. Verify DHT is working (DHT-based discovery)
4. Check peer reputation (low-quality peers blacklisted)

### Debug Logging

Enable detailed P2P logging:

```bash
LOG_LEVEL=DEBUG
LIBP2P_DEBUG=true

python -m src.main
```

Logs include:
- Peer connections/disconnections
- Message pub/sub events
- DHT queries
- Circuit relay usage

## Security Considerations

### Transport Security

All P2P connections use:
- **Encryption**: TLS 1.3 or Noise protocol
- **Authentication**: Peer ID verification via cryptographic signatures
- **Integrity**: Message signing and verification

### Peer Validation

Validate peers before trusting:

```python
from src.p2p.node import P2PNode

# Check peer reputation
reputation = peer_reputation.get_score(peer_id)
if reputation < 0.5:
    logger.warning(f"Low reputation peer: {peer_id}")
```

### Rate Limiting

Protect against spam:

- Gossipsub has built-in rate limiting
- Blacklist peers that exceed thresholds
- Connection pool limits total connections

### Signature Verification

All envelopes are verified:

```python
from policy.gates import GateEnforcer

enforcer = GateEnforcer()
decision = enforcer.ingress_validate(envelope)

if not decision.allowed:
    logger.error(f"Invalid envelope: {decision.reason}")
```

## Performance Tuning

### Latency Optimization

For low-latency scenarios:

```bash
# Reduce gossipsub heartbeat interval (default: 1s)
GOSSIPSUB_HEARTBEAT_INTERVAL=0.5

# Use QUIC transport (faster handshake)
P2P_LISTEN_ADDR=/ip4/0.0.0.0/udp/4001/quic

# Increase peer connections
P2P_MAX_CONNECTIONS=150
```

### Throughput Optimization

For high-throughput scenarios:

```bash
# Increase gossipsub mesh degree
GOSSIPSUB_MESH_DEGREE_LOW=6
GOSSIPSUB_MESH_DEGREE=8
GOSSIPSUB_MESH_DEGREE_HIGH=12

# Batch messages (application-level)
# See src/bus/hybrid.py for batching logic
```

### Resource Optimization

For resource-constrained nodes:

```bash
# Reduce peer connections
P2P_MAX_CONNECTIONS=20

# Disable relay (client only)
P2P_CIRCUIT_RELAY_ENABLED=false

# Use NATS fallback for critical messages
NATS_FALLBACK=true
```

## Migration from NATS

### Phase 1: Hybrid Mode (Recommended)

Run both NATS and P2P in parallel:

```bash
P2P_ENABLED=true
P2P_PRIMARY=false  # NATS still primary
NATS_FALLBACK=true
```

**Benefits:**
- Zero downtime
- Gradual rollout
- Easy rollback

### Phase 2: P2P Primary

Switch to P2P as primary:

```bash
P2P_ENABLED=true
P2P_PRIMARY=true
NATS_FALLBACK=true  # Keep NATS as safety net
```

**Monitor for issues:**
- Message propagation rates
- Latency metrics
- Connection stability

### Phase 3: P2P Only

Remove NATS dependency:

```bash
P2P_ENABLED=true
P2P_PRIMARY=true
NATS_FALLBACK=false
```

**Prerequisites:**
- P2P proven stable in production
- All nodes upgraded
- Monitoring shows good metrics

## Conclusion

P2P mode enables truly decentralized CAN Swarm deployments:

✅ No central broker  
✅ Automatic NAT traversal  
✅ Self-organizing mesh  
✅ Global peer discovery  

For questions or issues, see:
- [Architecture Documentation](ARCHITECTURE.md)
- [API Reference](API.md)
- GitHub Issues: https://github.com/canswarm/agent-swarm/issues
