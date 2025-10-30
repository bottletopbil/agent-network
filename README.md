CAN Swarm — Project Overview and Implementation Plan
====================================================

1\. Project Purpose
-------------------

CAN Swarm (Cognitive Agent Network) is a framework for building **cooperative AI systems**—a network of autonomous agents that can coordinate, verify, and execute tasks collectively in a transparent and auditable way.

The long-term vision is to create a **federated, decentralized AI ecosystem** where many independent “minds” (AI agents, human operators, or organizations) can work together safely without needing to trust each other blindly.

At its core, the Swarm is designed to answer one question:

> “How can we let intelligent systems cooperate on shared goals, while maintaining full verifiability, replayability, and ethical control?”

To achieve this, the CAN Swarm stack is structured around three fundamental principles:

1.  **Auditability:** Every action or decision can be replayed exactly as it happened.
    
2.  **Authenticity:** Every message, artifact, and plan is cryptographically signed and traceable.
    
3.  **Determinism:** The same inputs always produce the same outputs—critical for trust and replication.
    

2\. The Vision: The “Swarm Lab” Analogy
---------------------------------------

Imagine a digital laboratory filled with specialized robots.Each robot (agent) performs a task—planning, reasoning, analyzing, or verifying results.They all communicate through an **intercom system** (the message bus) and everything they say or do is recorded by a **CCTV system** (the signed audit log).

In this lab:

*   No robot can fake an instruction—it must sign every message.
    
*   No event disappears—everything is logged and timestamped.
    
*   If you replay the footage, the entire process unfolds identically.
    

That is the foundation of the Swarm: a verifiable digital ecosystem for intelligent cooperation.

3\. Project Architecture Overview
---------------------------------

The CAN Swarm network is built as a set of modular components. Each layer is isolated but interoperable.

**Core Components:**

1.  **NATS JetStream (Message Bus)**
    
    *   The communication backbone for all agents.
        
    *   Supports publish/subscribe semantics and persistent message history.
        
    *   Functions as the “Intercom” for the Swarm.
        
2.  **Signed JSONL Audit Log (CCTV)**
    
    *   A continuous append-only ledger of every published and delivered message.
        
    *   Each log line includes cryptographic signatures for verification.
        
    *   Enables deterministic replay and forensic auditing.
        
3.  **Ed25519 Cryptography (Identity and Signatures)**
    
    *   Each agent has a private/public key pair.
        
    *   Used to sign every message and verify authenticity.
        
    *   Provides tamper-proof identity verification.
        
4.  **MinIO / S3 (CAS Artifact Store)**
    
    *   A content-addressable storage system where large files or AI outputs are saved by hash.
        
    *   Ensures reproducibility and immutability of all referenced data.
        
5.  **Automerge CRDT (Plan State Store)**
    
    *   A conflict-free shared document format for multi-agent planning.
        
    *   Allows agents to update shared plans concurrently without conflicts.
        
6.  **OPA → WASM (Policy Engine)**
    
    *   A rulebook that defines what agents are allowed to do.
        
    *   Enforced before any message or action is accepted by the system.
        
    *   Ensures every decision follows the same logic, gas limits, and ethical constraints.
        
7.  **etcd-Raft (Scoped Consensus)**
    
    *   A minimal consensus mechanism for “decisions” that need exclusive resolution.
        
    *   Guarantees at-most-one DECIDE per need or plan.
        
8.  **OpenTelemetry (Observability Layer)**
    
    *   Provides traceability and performance metrics for the entire system.
        
    *   Integrated with the audit log for real-time monitoring.
        

4\. What Version 1 (v1) Is
--------------------------

**CAN Swarm v1** is a _centrally coordinated but replayable prototype_—a controlled, single-lab environment that simulates a cooperative network.

The goal of v1 is not decentralization; it’s to **prove determinism, replayability, and auditability** in a single-node setup.

### v1 Goal

Create a working system that can complete one full mission loop:

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   NEED → PLAN → DECIDE → COMMIT → FINALIZE   `

and be **replayed from the signed logs** to produce identical results.

If replaying the log produces the same outcome, the Swarm is considered “trustworthy” at v1.

5\. What We Have Built So Far
-----------------------------

**Phase 1: Intercom + CCTV**

This phase is complete. It establishes the communication and logging foundation.

*   **NATS JetStream** is running locally (via Docker or Homebrew).
    
*   **Signed JSONL logging** captures all published and received messages.
    
*   **Ed25519 keypair** is generated for signing and verifying every event.
    
*   **Publisher and listener scripts** demonstrate message flow.
    
*   **Verification script** confirms that all signatures in the log are valid.
    

Every message now has:

*   A timestamp,
    
*   A subject and thread ID,
    
*   A payload hash,
    
*   A digital signature,
    
*   And a verifiable record in the audit trail.
    

The system can now:

*   Send messages between agents,
    
*   Record them securely,
    
*   Verify authenticity post-execution.
    

This completes the foundational layer: the Swarm’s **secure communication backbone**.

6\. Next Steps for Version 1
----------------------------

The next development phases will transform this backbone into a functioning cooperative system.

### Phase 2 — Envelopes & Message Rules

Create the **Envelope** schema that wraps every message with:

*   sender ID
    
*   message type (NEED, PLAN, DECIDE, COMMIT, etc.)
    
*   lamport clock (for ordering)
    
*   nonce (for uniqueness)
    
*   signature and capability tokens
    

This will standardize all message traffic and allow replay-based determinism.

### Phase 3 — Policy Capsule (Law Book)

Integrate **OPA → WASM** policies that verify:

*   Message structure and allowed types
    
*   Size and signature limits
    
*   CAS reference validity
    
*   Permission scopes
    

Each message will be evaluated against the same rulebook before being processed or accepted into the plan.

### Phase 4 — CAS Integration

Implement **MinIO/S3** for storing external artifacts such as:

*   AI-generated files (plans, summaries, results)
    
*   Logs, datasets, or images referenced by hash
    

Messages will carry only the artifact hash, not the data itself.

### Phase 5 — Shared Plan CRDT

Use **Automerge** to maintain a shared plan document that can be updated by multiple agents concurrently without conflicts.This is the whiteboard where agents will propose tasks, dependencies, and results.

### Phase 6 — Scoped Consensus (DECIDE)

Integrate **etcd-Raft** for the DECIDE stage:

*   Each “NEED” will have its own Raft shard for voting.
    
*   Only one DECIDE can exist per need.
    
*   Decisions are finalized and stored immutably in the log.
    

### Phase 7 — Replay Simulator

Create a **replay CLI** that replays any signed JSONL log to verify outcomes.Replays must reproduce the same final state deterministically, using only the recorded data and hashes (no new AI calls).

7\. Development Flow Summary
----------------------------

Each phase builds on the last.Below is a simple outline of the implementation order for v1:

1.  **Phase 1 (Done):** NATS + Signed Audit Logs
    
2.  **Phase 2:** Message Envelopes (structured + signed)
    
3.  **Phase 3:** Policy Engine (OPA→WASM)
    
4.  **Phase 4:** CAS (MinIO/S3 storage by hash)
    
5.  **Phase 5:** Shared Plan (Automerge CRDT)
    
6.  **Phase 6:** Scoped Consensus (Raft)
    
7.  **Phase 7:** Deterministic Replay CLI
    
8.  **Phase 8:** End-to-End Test — one mission from NEED → FINALIZE
    

8\. Example Demonstration Goal for v1
-------------------------------------

A minimal working demo should execute this full loop:

1.  **NEED:** “Classify these 10 text lines by category and summarize.”
    
2.  **Planner AI:** Generates a plan (“one worker, one output file”).
    
3.  **Worker AI:** Executes classification and uploads results to CAS.
    
4.  **DECIDE:** Consensus engine accepts the worker’s result.
    
5.  **FINALIZE:** The system signs off and stores the final outcome in the log.
    
6.  **REPLAY:** A replay of the signed log yields the same final output.
    

Success = same FINAL\_HASH after replay.

That’s the definition of correctness for v1.

9\. Long-Term Vision (Beyond v1)
--------------------------------

Once v1 proves deterministic collaboration, future versions will move toward **decentralization and federation**:

*   Multiple independent labs (nodes) connected through IPFS/libp2p.
    
*   DID-based identity and capability tokens.
    
*   On-chain or distributed consensus for finalization.
    
*   Self-hosted or cross-organization Swarms that coordinate safely across networks.
    

v1 is the “closed lab prototype.”v2+ will open the lab doors to the wider world.

10\. Summary
------------

At this point, CAN Swarm has a **fully functioning communication and verification core**.Agents can:

*   Talk (through NATS),
    
*   Record (via the signed audit log),
    
*   Verify (using Ed25519 signatures).
    

The next major step is to **wrap these communications in Envelopes** and begin building the **rule-based decision layer (policy engine)** that ensures every action follows the same logical structure.

Once those are complete, CAN Swarm v1 will be able to:

*   Accept a task (NEED),
    
*   Plan and decide cooperatively,
    
*   Finalize results deterministically,
    
*   And replay the entire process exactly as it happened.
    

This will mark the first verifiable demonstration of a **replayable, auditable AI Swarm.**
------------------------------------------------------------------------------------------