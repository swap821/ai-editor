import { describe, expect, it } from 'vitest';
import {
  ApprovalDecisionSurfaceAuthority,
  ProvenanceExplanationSurfaceAuthority,
  SovereignHeartbeatSurfaceAuthority,
  TruthfulMirrorAuthority,
} from './SovereignStatePanel';

describe('Phase 2 sovereign surface authorities', () => {
  it('normalizes only truthful mirror payloads and detects total outage', () => {
    const authority = new TruthfulMirrorAuthority();
    expect(authority.normalizeGovernance({ constitution: {} })).toEqual({ constitution: {} });
    expect(authority.normalizeGovernance([])).toBeNull();
    expect(authority.normalizeExecutor({ executor: { configured: true } })).toEqual({ configured: true });
    expect(authority.normalizeExecutor({ executor: null })).toBeNull();
    expect(authority.allUnavailable([{ status: 'rejected' }, { status: 'rejected' }])).toBe(true);
    expect(authority.allUnavailable([{ status: 'fulfilled' }, { status: 'rejected' }])).toBe(false);
  });

  it('owns pending decision counting without treating evidence surfaces as authority', () => {
    const authority = new ApprovalDecisionSurfaceAuthority();
    expect(authority.pendingCount({
      facts: [{ id: 1 }],
      curriculum: [{ fingerprint: 'skill-1' }],
      council: { missions: [{ pendingApprovals: [{ id: 'approval-1' }] }] },
      selfAnalysis: { proposals: [{ status: 'proposed' }, { status: 'accepted' }] },
    })).toBe(4);
  });

  it('projects provenance and heartbeat state through dedicated owners', () => {
    const provenance = new ProvenanceExplanationSurfaceAuthority().project({
      routingDecisions: [{ provider: 'ollama' }],
      privacyAudits: [{ provider: 'ollama', redacted_paths: 0 }],
    });
    expect(provenance.routingDecisions).toHaveLength(1);
    expect(provenance.privacyAudits).toHaveLength(1);

    const heartbeat = new SovereignHeartbeatSurfaceAuthority();
    expect(heartbeat.badge({ _status: 'measured', value: false })).toEqual({ className: 'ok', text: 'operational' });
    expect(heartbeat.badge({ _status: 'measured', value: true })).toEqual({ className: 'danger', text: 'STOPPED' });
    expect(heartbeat.badge({ _status: 'loading' })).toEqual({ className: 'warn is-pulsing', text: 'reconnecting...' });
  });
});
