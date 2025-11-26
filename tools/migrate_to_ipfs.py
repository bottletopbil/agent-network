#!/usr/bin/env python3
"""
IPFS Migration Tool

Migrates content from FileCAS to IPFS with hash-to-CID mapping and verification.
"""

import sys
import json
import logging
import argparse
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cas.ipfs_store import IPFSContentStore
from cas_core import FileCAS, sha256_hash

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IPFSMigration:
    """
    Handles migration of content from FileCAS to IPFS.
    
    Provides scanning, migration, mapping creation, and verification.
    """
    
    def __init__(self, ipfs_host: str = "127.0.0.1", ipfs_port: int = 5001):
        """
        Initialize migration tool.
        
        Args:
            ipfs_host: IPFS API host
            ipfs_port: IPFS API port
        """
        self.ipfs_store = IPFSContentStore(ipfs_host, ipfs_port, auto_pin=True)
        logger.info(f"IPFS migration tool initialized")
    
    def scan_file_cas(self, cas_dir: Path) -> List[Tuple[str, Path]]:
        """
        Scan FileCAS directory for stored artifacts.
        
        Args:
            cas_dir: Path to FileCAS directory
            
        Returns:
            List of (hash, file_path) tuples
        """
        cas_dir = Path(cas_dir)
        
        if not cas_dir.exists():
            logger.warning(f"CAS directory does not exist: {cas_dir}")
            return []
        
        artifacts = []
        
        # Walk the CAS directory
        for file_path in cas_dir.rglob('*'):
            if file_path.is_file():
                # The filename should be the hash
                file_hash = file_path.name
                
                # Verify it's a valid hash (64 char hex string for SHA256)
                if len(file_hash) == 64 and all(c in '0123456789abcdef' for c in file_hash):
                    artifacts.append((file_hash, file_path))
                    logger.debug(f"Found artifact: {file_hash}")
        
        logger.info(f"Scanned {cas_dir}: found {len(artifacts)} artifacts")
        return artifacts
    
    def migrate_to_ipfs(
        self,
        cas_dir: Path,
        verify_hash: bool = True
    ) -> Dict[str, str]:
        """
        Migrate all files from FileCAS to IPFS.
        
        Args:
            cas_dir: Path to FileCAS directory
            verify_hash: Verify file hash before migration
            
        Returns:
            Dictionary mapping old_hash → CID
        """
        cas_dir = Path(cas_dir)
        logger.info(f"Starting migration from {cas_dir} to IPFS...")
        
        # Scan for artifacts
        artifacts = self.scan_file_cas(cas_dir)
        
        if not artifacts:
            logger.warning("No artifacts found to migrate")
            return {}
        
        mappings = {}
        success_count = 0
        error_count = 0
        
        for file_hash, file_path in artifacts:
            try:
                # Read content
                content = file_path.read_bytes()
                
                # Verify hash matches if requested
                if verify_hash:
                    computed_hash = sha256_hash(content)
                    if computed_hash != file_hash:
                        logger.error(
                            f"Hash mismatch for {file_path}: "
                            f"expected {file_hash}, got {computed_hash}"
                        )
                        error_count += 1
                        continue
                
                # Add to IPFS
                cid = self.ipfs_store.put(content)
                
                # Store mapping
                mappings[file_hash] = cid
                success_count += 1
                
                logger.info(f"Migrated {file_hash} → {cid} ({len(content)} bytes)")
                
            except Exception as e:
                logger.error(f"Failed to migrate {file_hash}: {e}")
                error_count += 1
        
        logger.info(
            f"Migration complete: {success_count} successful, "
            f"{error_count} errors, {len(mappings)} mappings created"
        )
        
        return mappings
    
    def create_mapping_file(
        self,
        mappings: Dict[str, str],
        output_path: Path,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Write hash-to-CID mappings to JSON file.
        
        Args:
            mappings: Dictionary of old_hash → CID
            output_path: Path to output JSON file
            metadata: Optional metadata to include
        """
        output_path = Path(output_path)
        
        # Prepare output structure
        output_data = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "total_mappings": len(mappings),
            "metadata": metadata or {},
            "mappings": mappings
        }
        
        # Write to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open('w') as f:
            json.dump(output_data, f, indent=2, sort_keys=True)
        
        logger.info(f"Mapping file created: {output_path} ({len(mappings)} entries)")
    
    def load_mapping_file(self, mapping_path: Path) -> Dict[str, str]:
        """
        Load hash-to-CID mappings from JSON file.
        
        Args:
            mapping_path: Path to mapping JSON file
            
        Returns:
            Dictionary of old_hash → CID
        """
        mapping_path = Path(mapping_path)
        
        if not mapping_path.exists():
            raise FileNotFoundError(f"Mapping file not found: {mapping_path}")
        
        with mapping_path.open('r') as f:
            data = json.load(f)
        
        mappings = data.get("mappings", {})
        logger.info(f"Loaded {len(mappings)} mappings from {mapping_path}")
        
        return mappings
    
    def verify_migration(
        self,
        mapping_file: Path,
        cas_dir: Optional[Path] = None
    ) -> Tuple[int, int]:
        """
        Verify migrated content in IPFS.
        
        Args:
            mapping_file: Path to mapping JSON file
            cas_dir: Optional path to original CAS dir for content verification
            
        Returns:
            Tuple of (verified_count, error_count)
        """
        logger.info(f"Starting migration verification from {mapping_file}...")
        
        # Load mappings
        mappings = self.load_mapping_file(mapping_file)
        
        verified_count = 0
        error_count = 0
        
        # Load FileCAS if provided
        file_cas = FileCAS(cas_dir) if cas_dir else None
        
        for old_hash, cid in mappings.items():
            try:
                # Check if content exists in IPFS
                if not self.ipfs_store.exists(cid):
                    logger.error(f"Content not found in IPFS: {cid} (hash: {old_hash})")
                    error_count += 1
                    continue
                
                # Retrieve from IPFS
                ipfs_content = self.ipfs_store.get(cid)
                
                # Verify hash of IPFS content
                computed_hash = sha256_hash(ipfs_content)
                if computed_hash != old_hash:
                    logger.error(
                        f"Hash mismatch for CID {cid}: "
                        f"expected {old_hash}, got {computed_hash}"
                    )
                    error_count += 1
                    continue
                
                # Optionally verify against original FileCAS
                if file_cas and file_cas.exists(old_hash):
                    original_content = file_cas.get(old_hash)
                    if original_content != ipfs_content:
                        logger.error(
                            f"Content mismatch for {old_hash}: "
                            f"FileCAS vs IPFS content differ"
                        )
                        error_count += 1
                        continue
                
                verified_count += 1
                logger.debug(f"Verified {old_hash} → {cid}")
                
            except Exception as e:
                logger.error(f"Verification failed for {old_hash} → {cid}: {e}")
                error_count += 1
        
        logger.info(
            f"Verification complete: {verified_count} verified, "
            f"{error_count} errors out of {len(mappings)} total"
        )
        
        return verified_count, error_count
    
    def close(self):
        """Close IPFS connection"""
        if self.ipfs_store:
            self.ipfs_store.close()


def main():
    """Command-line interface for IPFS migration"""
    parser = argparse.ArgumentParser(
        description="Migrate FileCAS content to IPFS with hash-to-CID mapping"
    )
    
    parser.add_argument(
        '--cas-dir',
        type=Path,
        default=Path('.cas'),
        help='Path to FileCAS directory (default: .cas)'
    )
    
    parser.add_argument(
        '--output-mapping',
        type=Path,
        default=Path('cas_to_ipfs.json'),
        help='Output path for mapping file (default: cas_to_ipfs.json)'
    )
    
    parser.add_argument(
        '--ipfs-host',
        type=str,
        default='127.0.0.1',
        help='IPFS API host (default: 127.0.0.1)'
    )
    
    parser.add_argument(
        '--ipfs-port',
        type=int,
        default=5001,
        help='IPFS API port (default: 5001)'
    )
    
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify migration after completion'
    )
    
    parser.add_argument(
        '--verify-only',
        type=Path,
        help='Only verify existing migration from mapping file'
    )
    
    parser.add_argument(
        '--no-hash-check',
        action='store_true',
        help='Skip hash verification during migration'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Initialize migration tool
        migration = IPFSMigration(args.ipfs_host, args.ipfs_port)
        
        # Verify-only mode
        if args.verify_only:
            logger.info("Running verification only...")
            verified, errors = migration.verify_migration(
                args.verify_only,
                args.cas_dir if args.cas_dir.exists() else None
            )
            
            if errors > 0:
                logger.error(f"Verification failed with {errors} errors")
                sys.exit(1)
            else:
                logger.info(f"✓ All {verified} entries verified successfully")
                sys.exit(0)
        
        # Perform migration
        logger.info("Starting migration...")
        mappings = migration.migrate_to_ipfs(
            args.cas_dir,
            verify_hash=not args.no_hash_check
        )
        
        if not mappings:
            logger.warning("No content migrated")
            sys.exit(1)
        
        # Create mapping file
        metadata = {
            "source": str(args.cas_dir),
            "ipfs_host": args.ipfs_host,
            "ipfs_port": args.ipfs_port
        }
        migration.create_mapping_file(mappings, args.output_mapping, metadata)
        
        # Verify if requested
        if args.verify:
            logger.info("Verifying migration...")
            verified, errors = migration.verify_migration(
                args.output_mapping,
                args.cas_dir
            )
            
            if errors > 0:
                logger.error(f"Verification found {errors} errors")
                sys.exit(1)
            else:
                logger.info(f"✓ All {verified} entries verified successfully")
        
        logger.info("Migration completed successfully!")
        migration.close()
        sys.exit(0)
        
    except KeyboardInterrupt:
        logger.info("Migration interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
