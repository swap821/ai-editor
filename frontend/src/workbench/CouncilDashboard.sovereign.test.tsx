/**
 * B3 sovereignty-surface tests: the CouncilDashboard's new Self-Analysis and
 * Sovereign State views against mocked live endpoints.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CouncilDashboard from './CouncilDashboard';

const PROPOSAL = {
  id: 7,
  target_path: 'aios/core/example.py',
  finding_type: 'complexity_hotspot',
  evidence: 'radon rank D on example()',
  proposed_zone: 'YELLOW',
  proposed_diff: '--- a/aios/core/example.py\n+++ b/aios/core/example.py',
  proposed_by: 'self-analysis',
  approved_by: null,
  status: 'proposed',
};

const AUTONOMY = {
  enabled: true,
  min_successes: 5,
  entries: [
    {
      signature: 'execute:pytest-training',
      action_type: 'execute_terminal',
      target_shape: 'pytest training_ground/*.py',
      success_count: 6,
      failure_count: 0,
      streak: 6,
      status: 'earned',
      earned_at: '2026-07-05',
      revoked_at: null,
      last_outcome_at: '2026-07-06',
    },
  ],
  summary: { earned: 1, probation: 0, revoked: 0 },
};

const FACTS = {
  proposals: [
    { id: 3, subject: 'operator', predicate: 'prefers', object: 'dark mode', source: 'chat', timestamp: 't' },
  ],
};

// Real trail_map() row shape (aios/memory/skills.py): skill_id + goal_pattern,
// NOT id/goal — the mock must exercise the live branch of the panel's fields.
const TRAILS = {
  trails: [
    {
      skill_id: 1,
      goal_pattern: 'verify sandbox tests',
      status: 'verified',
      strength: 0.91,
      quarantined: false,
    },
  ],
  fragments: [],
  summary: { verified: 1, candidate: 0 },
};

const CURRICULUM = {
  proposals: [
    {
      fingerprint: 'fp-1',
      skill_name: 'refactoring',
      level: 2,
      prompt: 'extract a helper from…',
      rationale: 'repeated failures',
      source_pattern: 'x',
      difficulty_delta: 1,
    },
  ],
};

const REPO_MAP = {
  available: true,
  localOnly: true,
  activation: 'proposal/evidence',
  trustedMemoryActivated: false,
  lastScan: {
    root: 'C:/repo',
    generatedAt: '2026-07-08T00:00:00Z',
    purpose: 'AI Editor - local-first AI OS',
    stack: ['FastAPI', 'React'],
    keyFileCount: 6,
    evidenceFileCount: 12,
    suggestedImprovementCount: 2,
  },
};

const RESOURCE = {
  mode: 'conservation',
  cloud_calls: 1,
  estimated_cost: 0.04,
  worker_count: 2,
  cpu_pressure: null,
  memory_pressure: null,
  cloud_allowed: false,
  reason: 'resource mode conservation blocks cloud',
  source: 'process_default',
};

const HIBERNATION = {
  configuredMode: 'conservation',
  hibernationMode: 'hibernation',
  localOnly: true,
  writesAllowed: false,
  cloudAllowed: false,
  lastRun: {
    ranAt: '2026-07-08T00:00:00Z',
    mode: 'hibernation',
    localOnly: true,
    writesPerformed: false,
    cloudCalls: 0,
    proposalCount: 3,
    projectPassport: { skipped: false, activation: 'proposal/evidence' },
    resourceMode: 'hibernation',
  },
};


const V10_STATUS = {
  activation: 'proposal/evidence',
  authority: 'proposal/evidence',
  localOnly: true,
  cloudCalls: 0,
  writesPerformed: false,
  canAuthorize: false,
  constitution: {
    available: true,
    casteCount: 7,
    frozenCoreProtected: true,
  },
  vulture: {
    available: true,
    lastScan: { findingCount: 2, cloudCalls: 0, writesPerformed: false },
  },
  ecosystem: {
    available: true,
    lastScan: { findingCount: 1, cloudCalls: 0, networkCalls: 0, writesPerformed: false },
  },
  councilMemory: {
    deliberationCount: 4,
  },
  symbolRepoMap: {
    activation: 'proposal/evidence',
    lastScan: { symbolCount: 123, evidenceFileCount: 12 },
  },
  metaLoop: {
    safetyStatus: 'ok',
    proposalCount: 3,
  },
};
const GOVERNANCE = {
  constitution: {
    constitution_id: { value: 'constitution:operator-1', status: 'measured', source: 'constitution_snapshot' },
    version: { value: 1, status: 'measured', source: 'constitution_snapshot' },
    ratified_by_operator_id: { value: 'operator-1', status: 'measured', source: 'constitution_snapshot' },
    snapshot_digest: { value: 'a'.repeat(64), status: 'measured', source: 'constitution_snapshot' },
    foundation_laws_count: { value: 5, status: 'measured', source: 'constitution_snapshot' },
  },
  emergencyStop: {
    engaged: { value: false, status: 'measured', source: 'emergency_stop_state' },
    generation: { value: 0, status: 'measured', source: 'emergency_stop_state' },
    reason: { value: null, status: 'unavailable', source: 'emergency_stop_state' },
    engaged_at: { value: null, status: 'unavailable', source: 'emergency_stop_state' },
  },
  providerHealth: [
    {
      provider: 'bedrock',
      reachable: { value: false, status: 'measured', source: 'provider_health_tracker' },
      circuit_state: { value: 'open', status: 'measured', source: 'provider_health_tracker' },
      recent_failure_count: { value: 3, status: 'measured', source: 'provider_health_tracker' },
      budget_remaining: { value: null, status: 'unavailable', source: 'provider_health_tracker' },
    },
  ],
  approvals: [
    {
      requested_action: { value: 'rollback', status: 'measured', source: 'capability_authority' },
      requesting_model: { value: null, status: 'unavailable', source: 'capability_authority' },
      mission_id: { value: 'mission-xyz', status: 'measured', source: 'capability_authority' },
      risk: { value: null, status: 'unavailable', source: 'capability_authority' },
      scope: { value: 'workspace/', status: 'measured', source: 'capability_authority' },
      reversibility: { value: null, status: 'unavailable', source: 'capability_authority' },
      verification_plan: { value: 'rollback_snapshot_restore', status: 'measured', source: 'capability_authority' },
      constitution_version: { value: null, status: 'unavailable', source: 'capability_authority' },
    },
  ],
  routingDecisions: [
    {
      turn_id: { value: 'turn-1', status: 'measured', source: 'development_tracker' },
      provider: { value: 'gemini', status: 'measured', source: 'development_tracker' },
      model: { value: 'gemini-2.5-flash', status: 'measured', source: 'development_tracker' },
      privacy: { value: 'cloud', status: 'measured', source: 'development_tracker' },
      task: { value: 'reasoning', status: 'measured', source: 'development_tracker' },
      auto: { value: true, status: 'measured', source: 'development_tracker' },
      recorded_at: { value: '2026-07-23T00:00:00+00:00', status: 'measured', source: 'development_tracker' },
    },
  ],
};

const EXECUTOR = {
  executor: {
    configured: { value: false, status: 'measured', source: 'executor_service_health' },
    reachable: { value: null, status: 'unavailable', source: 'executor_service_health' },
    runtime: { value: null, status: 'unavailable', source: 'executor_service_health' },
    reason: {
      value: 'private executor service is not configured',
      status: 'measured',
      source: 'executor_service_health',
    },
  },
};

const PHEROMONES = {
  pheromones: [
    {
      id: 1,
      type: 'success',
      resource: 'tests/test_castes.py',
      depositor: 'council',
      strength: 0.74,
      payload: {},
      created_at: '2026-07-08T00:00:00Z',
    },
  ],
};

const COUNCIL_MISSIONS = {
  missions: [
    {
      missionId: 'mission-1',
      mission: 'complex mission',
      status: 'awaiting_approval',
      recommendation: 'proceed',
      risk: 'YELLOW',
      pendingApprovals: [{ requestId: 'approval-1' }],
      royalDecree: {
        scout_contract: { metadata: { caste: 'forager' } },
        worker_contracts: [
          { metadata: { caste: 'builder' } },
          { metadata: { caste: 'scout' } },
        ],
      },
    },
  ],
  count: 1,
};

let posts: Array<{ url: string; body: string }> = [];

function mockFetch() {
  posts = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      if ((init?.method || 'GET') === 'POST') {
        posts.push({ url: u, body: String(init?.body ?? '') });
        return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
      }
      const payload = u.includes('/projects/passport/status')
        ? REPO_MAP
        : u.includes('/v10/status')
          ? V10_STATUS
          : u.includes('/mirror/governance')
            ? GOVERNANCE
          : u.includes('/mirror/executor')
            ? EXECUTOR
          : u.includes('/resource/status')
          ? RESOURCE
          : u.includes('/hibernation/status')
            ? HIBERNATION
            : u.includes('/pheromones/surface')
              ? PHEROMONES
              : u.includes('/council/missions')
                ? COUNCIL_MISSIONS
                : u.includes('/self-analysis/proposals')
        ? { proposals: [PROPOSAL] }
        : u.includes('/development/autonomy')
          ? AUTONOMY
          : u.includes('/memory/facts/pending')
            ? FACTS
            : u.includes('/development/trails')
              ? TRAILS
              : u.includes('/curriculum/proposals')
                ? CURRICULUM
                : { missions: [] };
      return { ok: true, status: 200, json: async () => payload } as unknown as Response;
    }),
  );
}

describe('CouncilDashboard sovereignty views', () => {
  beforeEach(() => {
    mockFetch();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('defaults to the Missions view with the three tabs visible', async () => {
    render(<CouncilDashboard />);
    expect(await screen.findByRole('tab', { name: 'Missions' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('tab', { name: 'Self-Analysis' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Sovereign State' })).toBeInTheDocument();
  });

  it('lists Self-Analysis proposals and rejects one via the live endpoint', async () => {
    render(<CouncilDashboard />);
    fireEvent.click(screen.getByRole('tab', { name: 'Self-Analysis' }));
    // The card's h3 mixes an svg icon with text nodes (breaks the default RTL
    // text matcher), so assert via the section's accessible name + the
    // single-text-node evidence line instead.
    expect(await screen.findByRole('region', { name: 'Proposal 7' })).toBeInTheDocument();
    expect(screen.getByText('radon rank D on example()')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    await waitFor(() =>
      expect(posts.some((p) => p.url.includes('/self-analysis/proposals/7/reject'))).toBe(true),
    );
  });

  it('renders sovereign sections and revokes an earned signature', async () => {
    render(<CouncilDashboard />);
    fireEvent.click(screen.getByRole('tab', { name: 'Sovereign State' }));
    expect(await screen.findByText(/Sovereign Organism v10/)).toBeInTheDocument();
    expect(screen.getByText(/7 castes · frozen core protected/)).toBeInTheDocument();
    expect(screen.getByText(/2 finding\(s\) · 0 cloud calls/)).toBeInTheDocument();
    expect(screen.getByText(/123 symbols · proposal\/evidence/)).toBeInTheDocument();
    expect(screen.getByText(/ok · 3 proposal\(s\)/)).toBeInTheDocument();
    expect(screen.getByText(/none can authorize action/)).toBeInTheDocument();
    expect(await screen.findByText(/Constitution & Emergency Stop/)).toBeInTheDocument();
    expect(screen.getByText('operational')).toBeInTheDocument();
    expect(screen.getByText('operator-1')).toBeInTheDocument();
    expect(screen.getByText('clear')).toBeInTheDocument();
    // The reason is genuinely unavailable (no stop ever engaged) -- must
    // render the honest fallback, never a blank or fabricated value.
    expect(screen.getAllByText('unavailable').length).toBeGreaterThan(0);
    expect(await screen.findByText(/Provider Health/)).toBeInTheDocument();
    expect(screen.getByText(/bedrock · 3 recent failure\(s\)/)).toBeInTheDocument();
    expect(screen.getByText('open')).toBeInTheDocument();
    expect(await screen.findByText(/Pending Approvals/)).toBeInTheDocument();
    expect(screen.getByText('rollback')).toBeInTheDocument();
    expect(screen.getByText('mission-xyz')).toBeInTheDocument();
    expect(screen.getByText('workspace/')).toBeInTheDocument();
    expect(await screen.findByText(/Provenance & Explanation/)).toBeInTheDocument();
    expect(screen.getByText(/gemini · gemini-2.5-flash · reasoning/)).toBeInTheDocument();
    expect(await screen.findByText(/Isolated Executor/)).toBeInTheDocument();
    expect(screen.getByText('not configured')).toBeInTheDocument();
    expect(
      screen.getByText('private executor service is not configured'),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Sovereign Superorganism v7/)).toBeInTheDocument();
    expect(screen.getByText(/AI Editor - local-first AI OS/)).toBeInTheDocument();
    expect(screen.getAllByText(/conservation/).length).toBeGreaterThan(0);
    expect(screen.getByText(/cloud blocked/)).toBeInTheDocument();
    expect(screen.getByText(/3 proposals/)).toBeInTheDocument();
    expect(screen.getByText(/success · tests\/test_castes.py · 74%/)).toBeInTheDocument();
    expect(screen.getByText(/builder x1, forager x1, scout x1/)).toBeInTheDocument();
    expect(screen.getByText(/4 pending item/)).toBeInTheDocument();
    expect(await screen.findByText(/Earned Autonomy/)).toBeInTheDocument();
    expect(screen.getByText(/execute_terminal/)).toBeInTheDocument();
    expect(screen.getByText(/operator — prefers — dark mode/)).toBeInTheDocument();
    expect(screen.getByText(/verify sandbox tests/)).toBeInTheDocument();
    expect(screen.getByText(/refactoring L2/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }));
    await waitFor(() =>
      expect(
        posts.some((p) =>
          p.url.includes('/development/autonomy/revoke?signature=execute%3Apytest-training'),
        ),
      ).toBe(true),
    );
  });

  it('refresh button reloads sovereign state from the real endpoints', async () => {
    render(<CouncilDashboard />);
    fireEvent.click(screen.getByRole('tab', { name: 'Sovereign State' }));
    await screen.findByText(/Constitution & Emergency Stop/);
    const fetchCallsBefore = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: 'Refresh sovereign state' }));

    await waitFor(() => {
      const fetchCallsAfter = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length;
      expect(fetchCallsAfter).toBeGreaterThan(fetchCallsBefore);
    });
    expect(await screen.findByText(/Constitution & Emergency Stop/)).toBeInTheDocument();
  });

  it('approves a pending fact through the quarantine endpoint', async () => {
    render(<CouncilDashboard />);
    fireEvent.click(screen.getByRole('tab', { name: 'Sovereign State' }));
    await screen.findByText(/operator — prefers — dark mode/);
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    // resolvedBy is REQUIRED by the backend's FactProposalResolveRequest —
    // assert the body carries it, not just that a POST fired.
    await waitFor(() => {
      const call = posts.find((p) => p.url.includes('/memory/facts/pending/3/approve'));
      expect(call).toBeDefined();
      expect(JSON.parse(call!.body)).toMatchObject({ resolvedBy: 'operator' });
    });
  });
});
