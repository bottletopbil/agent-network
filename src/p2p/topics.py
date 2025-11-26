"""
Topic Management for Gossipsub

Provides topic naming conventions, discovery, and filtering for
swarm communications.
"""

import re
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class SwarmTopic:
    """
    Structured swarm topic.
    
    Format: /swarm/thread/{thread_id}/{verb}
    """
    thread_id: str
    verb: str
    
    def to_string(self) -> str:
        """Convert to topic string"""
        return f"/swarm/thread/{self.thread_id}/{self.verb}"
    
    @classmethod
    def from_string(cls, topic: str) -> Optional['SwarmTopic']:
        """Parse topic string"""
        # Match pattern: /swarm/thread/{thread_id}/{verb}
        pattern = r'^/swarm/thread/([^/]+)/([^/]+)$'
        match = re.match(pattern, topic)
        
        if match:
            thread_id, verb = match.groups()
            return cls(thread_id=thread_id, verb=verb)
        return None
    
    def matches_filter(self, filter_dict: Dict[str, Any]) -> bool:
        """Check if topic matches filter criteria"""
        if 'thread_id' in filter_dict:
            if self.thread_id != filter_dict['thread_id']:
                return False
        
        if 'verb' in filter_dict:
            if self.verb != filter_dict['verb']:
                return False
        
        return True


# Standard verb types for swarm topics
class TopicVerbs:
    """Standard message type verbs for topics"""
    NEED = "need"
    PROPOSE = "propose"
    DECIDE = "decide"
    COMMIT = "commit"
    ATTEST = "attest"
    FINALIZE = "finalize"
    PATCH = "patch"
    CHALLENGE = "challenge"
    RECONCILE = "reconcile"
    ALL = "*"  # Subscribe to all verbs


def create_thread_topic(thread_id: str, verb: str) -> str:
    """
    Create topic string for thread and verb.
    
    Args:
        thread_id: Thread identifier
        verb: Message verb (NEED, PROPOSE, etc.)
        
    Returns:
        Topic string
    """
    topic = SwarmTopic(thread_id=thread_id, verb=verb)
    return topic.to_string()


def create_wildcard_topic(thread_id: str) -> str:
    """
    Create wildcard topic for all verbs in thread.
    
    Args:
        thread_id: Thread identifier
        
    Returns:
        Topic string with wildcard
    """
    return create_thread_topic(thread_id, TopicVerbs.ALL)


def parse_topic(topic: str) -> Optional[SwarmTopic]:
    """
    Parse topic string into structured form.
    
    Args:
        topic: Topic string
        
    Returns:
        SwarmTopic or None if invalid
    """
    return SwarmTopic.from_string(topic)


def filter_topics(topics: List[str], **filters) -> List[str]:
    """
    Filter topics by criteria.
    
    Args:
        topics: List of topic strings
        **filters: Filter criteria (thread_id, verb, etc.)
        
    Returns:
        Filtered list of topics
    """
    filtered = []
    
    for topic_str in topics:
        topic = parse_topic(topic_str)
        if topic and topic.matches_filter(filters):
            filtered.append(topic_str)
    
    return filtered


def get_thread_topics(thread_id: str) -> List[str]:
    """
    Get all standard topics for a thread.
    
    Args:
        thread_id: Thread identifier
        
    Returns:
        List of topic strings for all verbs
    """
    verbs = [
        TopicVerbs.NEED,
        TopicVerbs.PROPOSE,
        TopicVerbs.DECIDE,
        TopicVerbs.COMMIT,
        TopicVerbs.ATTEST,
        TopicVerbs.FINALIZE
    ]
    
    return [create_thread_topic(thread_id, verb) for verb in verbs]


def is_valid_topic(topic: str) -> bool:
    """
    Check if topic string is valid.
    
    Args:
        topic: Topic string
        
    Returns:
        True if valid swarm topic
    """
    return parse_topic(topic) is not None
