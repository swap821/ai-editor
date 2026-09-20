import { describe, expect, it } from 'vitest';
import { parseCouncilDetail, parseCouncilMissions, parseSkills } from './contracts';

// Serialized shape of aios/domain/learning/skill_contracts.py, never used as runtime fallback.
export const skillFixture = {
  skill_id: 'skill-format', version: 2, problem_signature: 'Format a Python module', state: 'candidate',
  applicability_conditions: { language: 'python' }, known_exclusions: ['generated files'], required_inputs: ['path'], required_project_state: { clean: 'true' },
  procedure: 'Format the admitted path and verify the resulting diff.', allowed_tools: ['format'], allowed_scope_pattern: 'src/*.py',
  expected_observations: ['formatter receipt'], verification_plan: null, escalation_conditions: ['scope mismatch'], source_trajectory_ids: ['trajectory-1'],
  confidence: 0.7, success_count: 3, failure_count: 1, last_validated_versions: ['python-3.12'],
};
export const missionFixture = { missionId: 'mission-1', mission: 'Repair the parser', status: 'deliberating', updatedAt: 1789400000 };
describe('actual public read contracts', () => {
  it('renders lifecycle identifiers and a string procedure; does not fabricate dates', () => {
    const result = parseSkills({ items: [skillFixture], status: 'available', source: 'durable_repository' });
    expect(result.items[0]).toMatchObject({ skill_id: 'skill-format', version: 2, state: 'candidate', procedure: skillFixture.procedure, updated_at: null });
  });
  it('does not equate malformed or contradictory data with a confirmed empty list', () => {
    expect(() => parseSkills({ items: [], status: 'available', source: 'durable_repository' })).toThrow();
    expect(() => parseSkills({ items: [{ name: 'old UI contract' }], status: 'available', source: 'durable_repository' })).toThrow();
    expect(parseSkills({ items: [], status: 'empty', source: 'durable_repository' }).items).toEqual([]);
  });
  it('retains unknown risk and verification; count is total readable reports', () => {
    expect(parseCouncilMissions({ missions: [missionFixture], count: 12 })).toEqual({ missions: [expect.objectContaining({ risk: null, verificationPassed: null, family: 'council' })], count: 12 });
  });
  it('keeps report and authoritative state separate and refuses a mismatched mission detail', () => {
    const d = { missionId: 'mission-1', summary: missionFixture, report: {}, ledger: null, pendingApprovals: [], kingDecision: null,
      missionAuthority: { state: 'approved', operatorId: 'operator-1', contractDigest: 'contract-1', runtimeContractDigest: null } };
    expect(parseCouncilDetail(d, 'mission-1')).toMatchObject({ summary: { status: 'deliberating' }, missionAuthority: { state: 'approved' } });
    expect(() => parseCouncilDetail(d, 'mission-2')).toThrow(/identity mismatch/);
  });
});
