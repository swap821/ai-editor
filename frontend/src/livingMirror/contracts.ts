/** Public read contracts. Unknown fields are never promoted into displayed claims. */
export type RecordValue = Record<string, unknown>;
export const isRecord = (value: unknown): value is RecordValue => !!value && typeof value === 'object' && !Array.isArray(value);
export const stringList = (value: unknown): value is string[] => Array.isArray(value) && value.every((v) => typeof v === 'string');
const record = (value: unknown, label: string): RecordValue => {
  if (!isRecord(value)) throw new Error(`Unsupported ${label} response`);
  return value;
};
const str = (value: unknown, label: string): string => {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`Missing ${label}`);
  return value;
};
const strings = (value: unknown, label: string): string[] => {
  if (!stringList(value)) throw new Error(`Unsupported ${label}`);
  return value;
};
const stringMap = (value: unknown, label: string): Record<string, string> => {
  const data = record(value, label);
  if (!Object.values(data).every((v) => typeof v === 'string')) throw new Error(`Unsupported ${label}`);
  return data as Record<string, string>;
};
const finite = (value: unknown, label: string): number => {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`Unsupported ${label}`);
  return value;
};
const optionalText = (value: unknown): string | null => typeof value === 'string' ? value : null;

export const skillStates = ['candidate', 'human_reviewed', 'qualified', 'active', 'probation', 'degraded', 'suspended', 'revoked', 'superseded', 'deprecated', 'blocked'] as const;
export interface SkillContract {
  skill_id: string;
  version: number;
  problem_signature: string;
  state: typeof skillStates[number];
  applicability_conditions: Record<string, string>;
  known_exclusions: string[];
  required_inputs: string[];
  required_project_state: Record<string, string>;
  procedure: string;
  allowed_tools: string[];
  allowed_scope_pattern: string;
  expected_observations: string[];
  verification_plan: RecordValue | null;
  escalation_conditions: string[];
  source_trajectory_ids: string[];
  confidence: number;
  success_count: number;
  failure_count: number;
  last_validated_versions: string[];
  created_at: string | null;
  updated_at: string | null;
}
export function parseSkills(value: unknown): { items: SkillContract[]; source: string; status: 'available' | 'empty' } {
  const data = record(value, 'skills');
  if (!Array.isArray(data.items) || !['available', 'empty'].includes(String(data.status)) || data.source !== 'durable_repository') throw new Error('Unsupported skills collection');
  if ((data.status === 'empty') !== (data.items.length === 0)) throw new Error('Inconsistent skills collection');
  const items = data.items.map((item) => {
    const s = record(item, 'skill');
    if (!skillStates.includes(s.state as SkillContract['state'])) throw new Error('Unsupported skill lifecycle');
    const version = finite(s.version, 'skill version');
    if (!Number.isSafeInteger(version) || version < 1) throw new Error('Unsupported skill version');
    return {
      skill_id: str(s.skill_id, 'skill ID'), version, problem_signature: str(s.problem_signature, 'problem signature'), state: s.state as SkillContract['state'],
      applicability_conditions: stringMap(s.applicability_conditions, 'applicability'), known_exclusions: strings(s.known_exclusions, 'exclusions'),
      required_inputs: strings(s.required_inputs, 'inputs'), required_project_state: stringMap(s.required_project_state, 'project state'),
      procedure: str(s.procedure, 'procedure'), allowed_tools: strings(s.allowed_tools, 'tools'), allowed_scope_pattern: str(s.allowed_scope_pattern, 'scope'),
      expected_observations: strings(s.expected_observations, 'observations'), verification_plan: s.verification_plan === null ? null : record(s.verification_plan, 'verification plan'),
      escalation_conditions: strings(s.escalation_conditions, 'escalation conditions'), source_trajectory_ids: strings(s.source_trajectory_ids, 'trajectories'),
      confidence: finite(s.confidence, 'confidence'), success_count: finite(s.success_count, 'success count'), failure_count: finite(s.failure_count, 'failure count'),
      last_validated_versions: strings(s.last_validated_versions, 'validated versions'), created_at: optionalText(s.created_at), updated_at: optionalText(s.updated_at),
    };
  });
  return { items, source: data.source, status: data.status as 'available' | 'empty' };
}

export interface CouncilMission {
  family: 'council';
  missionId: string;
  mission: string;
  status: string;
  risk: string | null;
  updatedAt: number | null;
  approvalNeeded: boolean | null;
  verificationPassed: boolean | null;
  verificationStrength: string | null;
  verificationMeetsFloor: boolean | null;
}
const booleanOrNull = (value: unknown) => typeof value === 'boolean' ? value : null;
function parseMission(value: unknown): CouncilMission {
  const m = record(value, 'Council mission');
  return { family: 'council', missionId: str(m.missionId, 'mission ID'), mission: str(m.mission, 'mission goal'), status: str(m.status, 'report status'),
    risk: optionalText(m.risk), updatedAt: typeof m.updatedAt === 'number' && Number.isFinite(m.updatedAt) ? m.updatedAt : null,
    approvalNeeded: booleanOrNull(m.approvalNeeded), verificationPassed: booleanOrNull(m.verificationPassed),
    verificationStrength: optionalText(m.verificationStrength), verificationMeetsFloor: booleanOrNull(m.verificationMeetsFloor) };
}
export function parseCouncilMissions(value: unknown): { missions: CouncilMission[]; count: number } {
  const data = record(value, 'Council list');
  if (!Array.isArray(data.missions)) throw new Error('Missing Council missions');
  const count = finite(data.count, 'mission count');
  if (!Number.isSafeInteger(count) || count < data.missions.length) throw new Error('Inconsistent mission count');
  const missions = data.missions.map(parseMission);
  if (new Set(missions.map((m) => m.missionId)).size !== missions.length) throw new Error('Duplicate mission identity');
  return { missions, count };
}
export interface CouncilDetail {
  missionId: string;
  summary: CouncilMission;
  report: RecordValue;
  ledger: RecordValue | null;
  pendingApprovals: { requestId: string; workerId: string; action: unknown; reason: string | null; createdAt: string | null }[];
  missionAuthority: { state: string; operatorId: string; contractDigest: string; runtimeContractDigest: string | null } | null;
  kingDecision: RecordValue | null;
}
export function parseCouncilDetail(value: unknown, expectedId: string): CouncilDetail {
  const d = record(value, 'Council detail');
  const summary = parseMission(d.summary);
  if (d.missionId !== expectedId || summary.missionId !== expectedId) throw new Error('Mission response identity mismatch');
  if (!Array.isArray(d.pendingApprovals)) throw new Error('Missing pending approval records');
  const a = d.missionAuthority === null ? null : record(d.missionAuthority, 'mission authority');
  return { missionId: expectedId, summary, report: record(d.report, 'mission report'), ledger: d.ledger === null ? null : record(d.ledger, 'mission ledger'),
    pendingApprovals: d.pendingApprovals.map((raw) => {
      const p = record(raw, 'pending approval');
      return { requestId: str(p.requestId, 'request ID'), workerId: str(p.workerId, 'worker ID'), action: p.action,
        reason: optionalText(p.reason), createdAt: optionalText(p.createdAt) };
    }),
    missionAuthority: a ? { state: str(a.state, 'authority state'), operatorId: str(a.operatorId, 'operator ID'), contractDigest: str(a.contractDigest, 'contract digest'), runtimeContractDigest: optionalText(a.runtimeContractDigest) } : null,
    kingDecision: d.kingDecision === null ? null : record(d.kingDecision, 'decision'),
  };
}
