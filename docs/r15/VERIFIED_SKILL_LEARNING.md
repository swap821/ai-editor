# Verified Skill Learning

## Overview
The AI-OS does not just execute scripts; it learns. The `SkillLibrary` maintains a catalog of "skills" which are re-usable, atomic capabilities parameterized for the workforce.

## Mechanics
- **Applicability Engine**: Dynamically matches a task profile to known skills using the `SkillApplicabilityEngine`.
- **Validation**: All new skills undergo a verification process. If a skill fails to produce deterministic outcomes, it is not promoted to the library.
- **DAG Execution**: Skills declare dependencies forming a DAG. The Engine guarantees safe parallelization where possible.
