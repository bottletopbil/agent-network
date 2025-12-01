"""
Bootstrap Nodes Configuration

Provides list of known bootstrap nodes for DHT and P2P network discovery.
"""

from typing import List, Dict


# Public IPFS bootstrap nodes (can be reused for our DHT)
IPFS_BOOTSTRAP_NODES = [
    "/dnsaddr/bootstrap.libp2p.io/p2p/QmNnooDu7bfjPFoTZYxMNLWUQJyrVwtbZg5gBMjTezGAJN",
    "/dnsaddr/bootstrap.libp2p.io/p2p/QmQCU2EcMqAqQPR2i9bChDtGNJchTbq5TbXJJ16u19uLTa",
    "/dnsaddr/bootstrap.libp2p.io/p2p/QmbLHAnMoJPWSCR5Zhtx6BHJX9KiKNN6tpvbUcqanj75Nb",
    "/dnsaddr/bootstrap.libp2p.io/p2p/QmcZf59bWwK5XFi76CZX8cbJ4BhTzzA3gU1ZjYZcYW3dwt",
]

# Custom swarm bootstrap nodes (would be deployed)
SWARM_BOOTSTRAP_NODES = [
    # Production bootstrap nodes would be listed here
    # "/ip4/bootstrap1.swarm.network/tcp/4001/p2p/12D3Koo...",
    # "/ip4/bootstrap2.swarm.network/tcp/4001/p2p/12D3Koo...",
]

# Local testing bootstrap nodes
LOCAL_BOOTSTRAP_NODES = [
    "/ip4/127.0.0.1/tcp/4001/p2p/12D3KooWLocalBootstrap1",
]


def get_bootstrap_nodes(
    include_ipfs: bool = True, include_swarm: bool = True, include_local: bool = False
) -> List[str]:
    """
    Get list of bootstrap nodes.

    Args:
        include_ipfs: Include IPFS public bootstrap nodes
        include_swarm: Include custom swarm bootstrap nodes
        include_local: Include local testing nodes

    Returns:
        List of multiaddr strings
    """
    nodes = []

    if include_swarm and SWARM_BOOTSTRAP_NODES:
        nodes.extend(SWARM_BOOTSTRAP_NODES)

    if include_ipfs:
        nodes.extend(IPFS_BOOTSTRAP_NODES)

    if include_local:
        nodes.extend(LOCAL_BOOTSTRAP_NODES)

    return nodes


def parse_multiaddr(multiaddr: str) -> Dict[str, str]:
    """
    Parse multiaddr into components.

    Args:
        multiaddr: Multiaddr string

    Returns:
        Dictionary with protocol, host, port, peer_id
    """
    # Simple parsing for /ip4/{host}/tcp/{port}/p2p/{peer_id}
    parts = multiaddr.split("/")

    result = {}

    for i, part in enumerate(parts):
        if part == "ip4" and i + 1 < len(parts):
            result["host"] = parts[i + 1]
        elif part == "tcp" and i + 1 < len(parts):
            result["port"] = int(parts[i + 1])
        elif part == "p2p" and i + 1 < len(parts):
            result["peer_id"] = parts[i + 1]
        elif part == "dnsaddr" and i + 1 < len(parts):
            result["dns"] = parts[i + 1]

    return result
