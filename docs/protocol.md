# Contract Net Protocol (CNP)

TactixNet implements the Contract Net Protocol for decentralized role assignment.

## Cycle

1. **Task Announcement** — Orchestrator decomposes squad objective into role-tasks (flank, distract, stealth-cover, overwatch, breach).
2. **Bidding** — Each agent computes a utility score from local perception only (no global state).
3. **Award** — Highest utility bid wins each task; conflict resolution prevents duplicate role/corridor assignment.
4. **Commit** — Versioned `SquadDirective` broadcast with monotonic `directive_seq`.

## Utility Functions

Each role has a dedicated utility function in `agents/utility.py`:

- **Flank** — High when calm, reduced when compromised
- **Distract** — High when compromised or under threat
- **Stealth-cover** — High in calm/suspicious states
- **Overwatch** — Scales with visibility polygon coverage
- **Breach** — Scales with ammo ratio, penalized when compromised

## Timeout Policy

Bid collection uses `asyncio.wait_for` with a hard timeout (default 40ms). Slow agents forfeit their bid rather than stalling the squad.

## Channels

- `squad:{id}:perception` — Agent perception frames
- `squad:{id}:intents` — Bid broadcasts
- `squad:{id}:directives` — Committed squad directives
