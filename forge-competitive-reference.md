# Forge Competitive Reference: Agent Memory & Engineering Context

**Purpose:** Reference and guiding artifact for Forge architecture.

## 1. Why this document exists

Forge is **not copying these products**.

These systems are reference points only. Use this document when Forge
reaches a design problem involving agent memory, cross-agent context,
engineering knowledge, retrieval, provenance, or agent actions.

The rule is:

> Learn from existing systems, understand their trade-offs, then make an
> independent Forge decision.

Do not introduce a feature merely because another product has it.

------------------------------------------------------------------------

## 2. Market signal

The market is converging around a common problem:

**AI coding agents are effective within a session but lose useful
engineering knowledge between sessions and across agents.**

Several products now explicitly target shared or persistent engineering
memory:

-   threadctx: shared memory across Claude Code, Cursor, and other MCP
    clients.
-   Engram: persistent/shared engineering memory for coding agents.
-   agentmemory: persistent memory server usable by agents through MCP,
    hooks, or REST.
-   Memco: governed shared memory that captures lessons from agent work
    and reuses them across models/tools/teams.
-   Roadie Context: broader engineering context infrastructure exposed
    to agents through MCP.
-   Cross-Agent Memory: repository-level, verified knowledge shared
    across different coding-agent systems.

This validates the problem space. It does **not** establish Forge's
product strategy.

------------------------------------------------------------------------

## 3. Reference architecture patterns

### Pattern A: Shared MCP memory

Representative: threadctx.

``` text
Claude Code ──┐
Cursor ───────┤
Codex ────────┤
Other MCP ────┘
       |
       v
   MCP Memory Server
       |
       v
 Shared project/team memory
```

Important ideas:

-   MCP provides a portable agent boundary.
-   Agents explicitly write useful learnings.
-   Agents query memory before risky or repeated work.
-   Git history can provide a fallback capture mechanism.
-   Local and cloud modes can coexist.
-   Project instruction files can encourage agents to query memory
    because MCP is fundamentally pull-based.

Forge lesson:

**MCP is a strong future interface for Forge agent actions.**

Do not make Forge dependent on a single coding agent.

------------------------------------------------------------------------

## 4. Pattern B: Lifecycle hooks + persistent memory

Representative: agentmemory / some Engram implementations.

``` text
Agent lifecycle
      |
      v
Hooks / events
      |
      v
Observations
      |
      v
Distillation / extraction
      |
      v
Curated memory
      |
      v
Persistent store
      |
      v
Retrieval
      |
      v
Next agent session
```

Important ideas:

-   Memory can be captured automatically from lifecycle events.
-   Raw observations are different from durable memory.
-   Multiple agent clients can use one memory service.
-   Retrieval may combine keyword, semantic, and graph techniques.
-   Some systems expose many tools through MCP.

Forge lesson:

**Capture should eventually be evidence-driven, not dependent on an
agent remembering to manually save a lesson.**

But Phase 1 should not start with a large hook/retrieval infrastructure.

------------------------------------------------------------------------

## 5. Pattern C: Governed engineering memory

Representative: Memco.

``` text
Agent work
    |
    v
Trace / outcome
    |
    v
Candidate lesson
    |
    v
Trust + scope + dedup + version
    |
    v
Reviewed durable memory
    |
    v
Relevant memory to next agent
```

Important ideas:

-   Not every trace deserves to become memory.
-   Memory needs scope and ownership.
-   Useful lessons should be distinguishable from raw activity.
-   Memory can become stale.
-   Memory may need ranking, decay, audit, and provenance.
-   The goal is compounding engineering knowledge, not storing
    everything.

Forge lesson:

**Context Bank should contain durable engineering knowledge, not an
indiscriminate transcript dump.**

This strongly supports the distinction:

-   Session = historical record of work.
-   Context Entry = durable engineering statement.

------------------------------------------------------------------------

## 6. Pattern D: Engineering context graph

Representative: Roadie Context.

``` text
Git / cloud / incidents / org data / integrations
                    |
                    v
             Context Store
                    |
                    v
              Context Graph
                    |
                    v
                  MCP
                    |
                    v
                  Agent
```

Important ideas:

-   The system can model current engineering entities and relationships.
-   Context can come from multiple systems of record.
-   Agents can progressively retrieve only the context required for a
    task.
-   Agent tool calls can be recorded as sessions.
-   Context and actions can be separated into different capabilities.

Forge lesson:

**Forge can eventually move beyond memory into engineering context +
agent actions.**

However, a full engineering graph is not required for Phase 1.

------------------------------------------------------------------------

## 7. Pattern E: Git-native shared memory

Representative: Cross-Agent Memory and similar open-source projects.

``` text
Agent A ──┐
Agent B ──┼──> verified project knowledge
Agent C ──┘             |
                         v
                       Git
                         |
                         v
                 Next agent/client
```

Important ideas:

-   Shared knowledge can remain client-neutral.
-   Git can provide versioning, history, and portability.
-   Native agent memory should remain separate from shared project
    memory.
-   Current code/tests/runtime evidence should outrank potentially stale
    memory.
-   Explicit lifecycle operations can include bootstrap, recall,
    promote, reconcile, consolidate, retire, and audit.

Forge lesson:

**Canonical knowledge needs provenance, lifecycle, and evidence.**

Forge does not need to use Git as its Context Bank, but the lifecycle
ideas are valuable.

------------------------------------------------------------------------

## 8. Cross-agent support

Cross-agent operation is no longer unusual.

Observed interfaces include:

-   MCP
-   REST
-   agent-specific plugins
-   lifecycle hooks
-   repository instruction files such as AGENTS.md / CLAUDE.md
-   Git-based workflows

The common architecture is:

``` text
Many agents
    |
    v
Portable adapter boundary
    |
    v
Shared context/memory service
```

Forge should follow this principle.

**Forge should be agent-agnostic.**

Claude Code, Codex, Cursor, Gemini, and future agents should be clients
of Forge rather than architectural dependencies inside Forge.

------------------------------------------------------------------------

## 9. What existing systems teach us

### Lesson 1: Memory is not the same as history

Raw session history answers:

> What happened?

Durable context answers:

> What do we currently know?

Forge should keep these separate.

### Lesson 2: Shared memory needs scope

Memory should be scoped to an appropriate boundary.

Forge's Feature is the primary engineering ownership boundary.

### Lesson 3: Retrieval should be selective

Do not send the entire Context Bank to an agent.

Retrieve the relevant context and serialize it into a compact
agent-facing representation.

### Lesson 4: Memory needs provenance

A durable statement should be traceable to evidence such as:

-   source session
-   author/agent
-   changed files
-   commit
-   test result
-   other evidence available to Forge

### Lesson 5: Memory can become wrong

Future Forge versions will need:

-   versioning
-   superseding
-   conflict detection
-   stale/retired state
-   auditability

### Lesson 6: Agent actions matter

The interesting evolution is:

``` text
Memory
   |
   v
Context
   |
   v
Actions
   |
   v
Engineering automation
```

Forge should not stop at "remember things."

------------------------------------------------------------------------

## 10. What Forge should NOT copy

Do not copy:

-   another product's schema
-   another product's branding or terminology
-   arbitrary MCP tool counts
-   complex vector/graph infrastructure before it is justified
-   their memory lifecycle blindly
-   their pricing model
-   their storage architecture
-   their UI
-   their agent-specific integrations

These systems are **reference implementations and market signals**, not
Forge specifications.

------------------------------------------------------------------------

## 11. Forge's current independent model

The current Forge direction is:

``` text
Coding Agent / Engineer
          |
          v
       Session
          |
          v
 Context Generator
          |
          v
 Context Validator
          |
          v
  Typed Context Entries
          |
          v
     Context Bank
          |
          +------> Agent retrieval/actions
```

Feature remains the ownership boundary:

``` text
Feature
  |
  +-- Sessions
  |
  +-- Context Entries
  |
  +-- Access control
  |
  +-- Future agent actions
```

The long-term direction is:

``` text
Engineering systems
        |
        v
      Forge
        |
   +----+----+
   |         |
Context    Actions
   |         |
   +----+----+
        |
        v
 Humans + AI agents
```

------------------------------------------------------------------------

## 12. Questions to ask when Forge gets stuck

When facing an architectural problem, consult this document and ask:

1.  Does an existing system already solve a similar problem?
2.  What is the simplest mechanism they use?
3.  What trade-off did they accept?
4.  Is the problem actually relevant to Forge's current phase?
5.  Can we implement the smallest useful version first?
6.  Does the solution preserve Feature ownership and authorization?
7.  Does it preserve provenance and versioning?
8.  Can the design remain agent-agnostic?
9.  Are we solving a real Forge problem, or copying a competitor because
    it looks sophisticated?

------------------------------------------------------------------------

## 13. Current reference map

  -----------------------------------------------------------------------
  Reference               Primary idea            Use it when thinking
                                                  about
  ----------------------- ----------------------- -----------------------
  threadctx               Shared MCP memory       Cross-agent
                                                  connectivity,
                                                  lightweight memory

  Engram                  Persistent agent memory Lifecycle capture,
                                                  durable memory

  agentmemory             Hooks + MCP +           Automatic capture and
                          persistent memory       retrieval

  Memco                   Governed engineering    Trust, scope,
                          memory                  promotion, decay

  Roadie Context          Engineering context     Context graph,
                          infrastructure          integrations, agent
                                                  actions

  Cross-Agent Memory      Verified client-neutral Evidence,
                          project memory          reconciliation,
                                                  Git-native knowledge
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 14. Final principle

Forge should learn from the market without becoming a clone of the
market.

The reference systems prove that:

-   persistent agent memory is useful;
-   cross-agent memory is technically feasible;
-   MCP is a practical agent integration boundary;
-   governance and provenance matter;
-   engineering context can become an agent capability layer.

Forge's job is to decide what combination of these ideas is right for
its own model.

**Use competitors as a compass, not as a blueprint.**
