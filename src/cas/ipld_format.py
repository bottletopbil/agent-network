"""
IPLD Format for Envelopes and Threads

Provides IPLD (InterPlanetary Linked Data) formatting for envelopes and threads,
enabling content-addressed DAG structures with CID links.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class EnvelopeIPLD:
    """
    Converts envelopes to/from IPLD DAG format.

    IPLD uses CID links to reference content, creating a Merkle DAG structure
    that enables verifiable, content-addressed data.
    """

    @staticmethod
    def to_ipld(envelope: Dict[str, Any], cas_store=None) -> Dict[str, Any]:
        """
        Convert envelope to IPLD DAG format.

        Replaces large payload content with CID links using the {"/": cid} format.

        Args:
            envelope: Envelope dictionary
            cas_store: Optional CAS store for storing payload content

        Returns:
            IPLD-formatted dictionary with CID links
        """
        ipld_envelope = {}

        # Copy basic fields
        for key in [
            "v",
            "id",
            "thread_id",
            "kind",
            "lamport",
            "ts_ns",
            "sender_pk_b64",
            "policy_engine_hash",
            "nonce",
            "sig_pk_b64",
            "sig_b64",
        ]:
            if key in envelope:
                ipld_envelope[key] = envelope[key]

        # Handle payload - convert to CID link if CAS store provided
        if "payload" in envelope:
            payload = envelope["payload"]

            if cas_store and isinstance(payload, dict):
                # Store payload in CAS and link via CID
                payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
                payload_cid = cas_store.put(payload_bytes)

                # IPLD link format: {"/": cid}
                ipld_envelope["payload"] = {"/": payload_cid}
                logger.debug(f"Linked payload as CID: {payload_cid}")
            else:
                # Keep payload inline if no CAS or not a dict
                ipld_envelope["payload"] = payload

        # Keep payload_hash for verification
        if "payload_hash" in envelope:
            ipld_envelope["payload_hash"] = envelope["payload_hash"]

        # Add optional policy fields
        for key in ["policy_capsule_hash", "policy_eval_digest"]:
            if key in envelope:
                ipld_envelope[key] = envelope[key]

        return ipld_envelope

    @staticmethod
    def from_ipld(ipld_data: Dict[str, Any], cas_store=None) -> Dict[str, Any]:
        """
        Reconstruct envelope from IPLD DAG format.

        Resolves CID links to retrieve original content.

        Args:
            ipld_data: IPLD-formatted dictionary
            cas_store: CAS store for resolving CID links

        Returns:
            Reconstructed envelope dictionary
        """
        envelope = {}

        # Copy all fields
        for key, value in ipld_data.items():
            # Check if value is a CID link
            if isinstance(value, dict) and "/" in value:
                # Resolve CID link
                cid = value["/"]

                if cas_store:
                    try:
                        # Retrieve content from CAS
                        content_bytes = cas_store.get(cid)

                        # Parse as JSON if it's the payload
                        if key == "payload":
                            content = json.loads(content_bytes.decode("utf-8"))
                            envelope[key] = content
                            logger.debug(f"Resolved payload from CID: {cid}")
                        else:
                            envelope[key] = content_bytes
                    except Exception as e:
                        logger.error(f"Failed to resolve CID {cid}: {e}")
                        envelope[key] = value  # Keep as link if resolution fails
                else:
                    # No CAS store, keep as link
                    envelope[key] = value
            else:
                envelope[key] = value

        return envelope

    @staticmethod
    def is_ipld_link(value: Any) -> bool:
        """Check if a value is an IPLD CID link"""
        return isinstance(value, dict) and "/" in value

    @staticmethod
    def get_cid_from_link(link: Dict[str, str]) -> Optional[str]:
        """Extract CID from IPLD link"""
        if isinstance(link, dict) and "/" in link:
            return link["/"]
        return None


class ThreadIPLD:
    """
    Stores entire thread as IPLD DAG with linked envelopes.

    Creates a Merkle DAG structure where each envelope links to the previous,
    forming a verifiable chain.
    """

    def __init__(self, cas_store=None):
        """
        Initialize Thread IPLD handler.

        Args:
            cas_store: CAS store for storing envelope content
        """
        self.cas_store = cas_store

    def envelopes_to_dag(
        self, envelopes: List[Dict[str, Any]], thread_id: str
    ) -> Dict[str, Any]:
        """
        Convert list of envelopes to IPLD DAG structure.

        Args:
            envelopes: List of envelope dictionaries
            thread_id: Thread identifier

        Returns:
            Thread DAG with envelope links
        """
        envelope_cids = []

        # Convert each envelope to IPLD and store
        for envelope in envelopes:
            # Convert to IPLD format
            ipld_envelope = EnvelopeIPLD.to_ipld(envelope, self.cas_store)

            # Store envelope in CAS
            if self.cas_store:
                envelope_bytes = json.dumps(ipld_envelope, sort_keys=True).encode(
                    "utf-8"
                )
                envelope_cid = self.cas_store.put(envelope_bytes)
                envelope_cids.append(envelope_cid)
                logger.debug(f"Stored envelope in DAG: {envelope_cid}")
            else:
                # Without CAS, include inline
                envelope_cids.append(ipld_envelope)

        # Create thread DAG
        thread_dag = {
            "thread_id": thread_id,
            "envelope_count": len(envelopes),
            "envelopes": [
                {"/": cid} if isinstance(cid, str) else cid for cid in envelope_cids
            ],
            "version": "1.0",
        }

        return thread_dag

    def dag_to_envelopes(self, thread_dag: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Reconstruct envelopes from thread DAG.

        Args:
            thread_dag: Thread DAG structure

        Returns:
            List of reconstructed envelopes
        """
        envelopes = []

        for envelope_link in thread_dag.get("envelopes", []):
            # Check if it's a CID link
            if isinstance(envelope_link, dict) and "/" in envelope_link:
                cid = envelope_link["/"]

                if self.cas_store:
                    try:
                        # Retrieve envelope from CAS
                        envelope_bytes = self.cas_store.get(cid)
                        ipld_envelope = json.loads(envelope_bytes.decode("utf-8"))

                        # Reconstruct from IPLD
                        envelope = EnvelopeIPLD.from_ipld(ipld_envelope, self.cas_store)
                        envelopes.append(envelope)
                    except Exception as e:
                        logger.error(f"Failed to retrieve envelope {cid}: {e}")
                else:
                    logger.warning(f"No CAS store to resolve envelope CID: {cid}")
            else:
                # Inline envelope
                envelope = EnvelopeIPLD.from_ipld(envelope_link, self.cas_store)
                envelopes.append(envelope)

        return envelopes

    def store_thread_dag(self, thread_dag: Dict[str, Any]) -> Optional[str]:
        """
        Store entire thread DAG in CAS.

        Args:
            thread_dag: Thread DAG to store

        Returns:
            CID of stored thread DAG (root)
        """
        if not self.cas_store:
            logger.warning("No CAS store available")
            return None

        try:
            dag_bytes = json.dumps(thread_dag, sort_keys=True).encode("utf-8")
            root_cid = self.cas_store.put(dag_bytes)
            logger.info(f"Stored thread DAG: {root_cid}")
            return root_cid
        except Exception as e:
            logger.error(f"Failed to store thread DAG: {e}")
            return None

    def load_thread_dag(self, root_cid: str) -> Optional[Dict[str, Any]]:
        """
        Load thread DAG from CAS by root CID.

        Args:
            root_cid: Root CID of thread DAG

        Returns:
            Thread DAG structure
        """
        if not self.cas_store:
            logger.warning("No CAS store available")
            return None

        try:
            dag_bytes = self.cas_store.get(root_cid)
            thread_dag = json.loads(dag_bytes.decode("utf-8"))
            logger.info(f"Loaded thread DAG: {root_cid}")
            return thread_dag
        except Exception as e:
            logger.error(f"Failed to load thread DAG: {e}")
            return None


@dataclass
class IPLDLink:
    """Represents an IPLD CID link"""

    cid: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to IPLD link format"""
        return {"/": self.cid}

    @classmethod
    def from_dict(cls, link: Dict[str, str]) -> "IPLDLink":
        """Create from IPLD link format"""
        return cls(cid=link["/"])
