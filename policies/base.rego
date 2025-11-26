# CAN Swarm Base Policy
#
# Validates all envelopes against basic rules:
# - Allowed message kinds
# - Payload size limits
# - Basic structural requirements

package swarm.policy

# Default deny - must explicitly allow
default allow = false

# Allow envelope if it passes all checks
allow {
    input.kind in allowed_kinds
    input.payload_size < max_payload_size
    has_required_fields
}

# Allowed message kinds in the CAN Swarm protocol
allowed_kinds = {
    "NEED",
    "PROPOSE",
    "CLAIM",
    "COMMIT",
    "ATTEST",
    "DECIDE",
    "FINALIZE",
    "YIELD",
    "RELEASE",
    "UPDATE_PLAN",
    "ATTEST_PLAN",
    "CHALLENGE",
    "INVALIDATE",
    "RECONCILE",
    "CHECKPOINT"
}

# Maximum payload size (1MB)
max_payload_size = 1048576

# Required fields check
has_required_fields {
    input.kind
    input.thread_id
    input.lamport
    input.actor_id
}

# Deny reasons for debugging
deny_reason = reason {
    not input.kind in allowed_kinds
    reason := sprintf("Invalid message kind: %v", [input.kind])
}

deny_reason = reason {
    input.payload_size >= max_payload_size
    reason := sprintf("Payload too large: %v bytes (max: %v)", [input.payload_size, max_payload_size])
}

deny_reason = reason {
    not has_required_fields
    reason := "Missing required fields (kind, thread_id, lamport, actor_id)"
}

# Version info
policy_version = "1.0.0"
