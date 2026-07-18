# Frontier Intelligence Hiring

## Overview
The Hiring module orchestrates the recruitment of frontier intelligence (large remote models) for specific, bounded missions. It interfaces with the Local Workforce to grant temporary, tightly-scoped access.

## Process
1. **Proposal**: A system component creates a `HiringProposal` defining the scope, budget, and required intelligence class.
2. **Approval**: The Human Sovereign (operator) reviews and approves the proposal.
3. **Execution**: The `HiringLedger` records the approval and authorizes temporary API usage for the requested model.

## Boundaries
- Models are restricted from viewing system core architecture unless explicitly requested and scoped by the Human Sovereign.
