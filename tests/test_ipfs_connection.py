"""
Test IPFS Connection and Configuration

Simple script to verify IPFS setup and connectivity.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cas.ipfs_config import IPFSClient, IPFSConfig


def test_ipfs_connection():
    """Test IPFS connection and basic operations"""
    print("🧪 Testing IPFS Connection...")
    print("=" * 60)

    # Create client
    config = IPFSConfig()
    print(f"📍 API URL: {config.get_api_url()}")
    print(f"🌐 Gateway URL: {config.get_gateway_url()}")
    print(f"📌 Pinning Strategy: {config.pinning_strategy.value}")
    print()

    client = IPFSClient(config)

    # Test connection
    print("🔌 Connecting to IPFS...")
    if not client.connect():
        print("❌ Failed to connect to IPFS daemon")
        print("ℹ️  Make sure IPFS is running:")
        print("   - Docker: docker-compose up -d ipfs")
        print("   - Local: ipfs daemon &")
        return False

    print("✅ Connected to IPFS!")
    print()

    # Get peer ID
    print("🆔 Getting peer ID...")
    peer_id = client.get_peer_id()
    if peer_id:
        print(f"✅ Peer ID: {peer_id}")
    else:
        print("❌ Failed to get peer ID")
        return False
    print()

    # Get stats
    print("📊 Getting node statistics...")
    stats = client.get_stats()
    if stats:
        print(f"✅ Stats:")
        print(f"   - Objects: {stats.get('num_objects', 'N/A')}")
        print(f"   - Repo Size: {stats.get('repo_size', 'N/A')} bytes")
        print(f"   - Storage Max: {stats.get('storage_max', 'N/A')} bytes")
    else:
        print("⚠️  Could not retrieve stats")
    print()

    # Test add and retrieve
    print("📝 Testing add and retrieve...")
    test_data = b"Hello from CAN Swarm IPFS!"

    cid = client.add_content(test_data, pin=True)
    if cid:
        print(f"✅ Added content: {cid}")

        retrieved = client.get_content(cid)
        if retrieved == test_data:
            print("✅ Retrieved content matches!")
        else:
            print("❌ Retrieved content doesn't match")
            return False
    else:
        print("❌ Failed to add content")
        return False
    print()

    # Test pinning
    print("📌 Testing pin operations...")
    pins = client.list_pins()
    if cid in pins:
        print(f"✅ Content is pinned ({len(pins)} total pins)")
    else:
        print("⚠️  Content not in pin list")
    print()

    # Cleanup
    print("🧹 Cleaning up test content...")
    if client.unpin_content(cid):
        print("✅ Unpinned test content")

    client.close()
    print()
    print("=" * 60)
    print("✅ All IPFS tests passed!")
    return True


if __name__ == "__main__":
    success = test_ipfs_connection()
    sys.exit(0 if success else 1)
