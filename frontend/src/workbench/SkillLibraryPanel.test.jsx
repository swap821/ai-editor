import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import SkillLibraryPanel from './SkillLibraryPanel';

const mocks = vi.hoisted(() => ({
  useResource: vi.fn(),
  parseSkills: vi.fn(),
  skillActions: vi.fn(),
}));

vi.mock('../livingMirror/contracts', () => ({ parseSkills: mocks.parseSkills }));
vi.mock('../livingMirror/resource', () => ({ useResource: mocks.useResource }));
vi.mock('../livingMirror/ResourceNotice', () => ({
  ResourceNotice: ({ resource, empty }) => (
    <div>{resource.status === 'empty' ? empty : resource.status}</div>
  ),
}));
vi.mock('../livingMirror/SkillActions', () => ({
  SkillActions: (props) => {
    mocks.skillActions(props);
    return <button onClick={props.refresh} disabled={!props.available}>Refresh skill</button>;
  },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('SkillLibraryPanel', () => {
  it('shows the empty notice and supplies an empty-items predicate to the resource hook', () => {
    mocks.useResource.mockReturnValue({ status: 'empty', data: { items: [] } });

    render(<SkillLibraryPanel />);

    expect(screen.getByRole('heading', { name: 'Experience & skills' })).toBeTruthy();
    expect(screen.getByText('The durable repository contains no skill versions.')).toBeTruthy();
    expect(screen.queryByRole('list')).toBeNull();

    const [url, parser, isEmpty] = mocks.useResource.mock.calls[0];
    expect(url).toBe('/api/v1/skills');
    expect(parser).toBe(mocks.parseSkills);
    expect(isEmpty({ items: [] })).toBe(true);
    expect(isEmpty({ items: [{}] })).toBe(false);
  });

  it('renders skill details and passes availability and refresh to its actions', () => {
    const refresh = vi.fn();
    const skill = {
      skill_id: 'skill-alpha',
      version: 2,
      problem_signature: 'Resolve a failing build',
      state: 'ready_for_review',
      applicability_conditions: { language: 'TypeScript' },
      known_exclusions: ['production'],
      required_inputs: ['logs'],
      required_project_state: { branch: 'clean' },
      procedure: 'Inspect the logs',
      allowed_scope_pattern: 'project',
      allowed_tools: ['compiler'],
      source_trajectory_ids: ['trace-1'],
      success_count: 3,
      failure_count: 1,
      escalation_conditions: ['missing logs'],
      verification_plan: { command: 'test' },
    };
    mocks.useResource.mockReturnValue({
      status: 'available',
      data: { items: [skill] },
      refresh,
    });

    render(<SkillLibraryPanel />);

    const item = within(screen.getByRole('list')).getByRole('listitem');
    expect(within(item).getByText('Resolve a failing build')).toBeTruthy();
    expect(within(item).getByText(/Version 2 · ready for review/)).toBeTruthy();
    expect(within(item).getByText('language: TypeScript')).toBeTruthy();
    expect(within(item).getByText('branch: clean')).toBeTruthy();
    expect(within(item).getByText('Inspect the logs')).toBeTruthy();
    expect(within(item).getByText('3 successes; 1 failures')).toBeTruthy();
    expect(within(item).getByText(/"command": "test"/)).toBeTruthy();
    expect(mocks.skillActions).toHaveBeenCalledWith({ skill, available: true, refresh });
    screen.getByRole('button', { name: 'Refresh skill' }).click();
    expect(refresh).toHaveBeenCalledOnce();
  });

  it('renders fallback details and disables actions when the resource is unavailable', () => {
    const refresh = vi.fn();
    const skill = {
      skill_id: 'skill-beta',
      version: 1,
      problem_signature: 'Investigate',
      state: 'draft',
      applicability_conditions: {},
      known_exclusions: [],
      required_inputs: [],
      required_project_state: {},
      procedure: 'Inspect',
      allowed_scope_pattern: 'local',
      allowed_tools: [],
      source_trajectory_ids: [],
      success_count: 0,
      failure_count: 0,
      escalation_conditions: [],
      verification_plan: null,
    };
    mocks.useResource.mockReturnValue({
      status: 'loading',
      data: { items: [skill] },
      refresh,
    });

    render(<SkillLibraryPanel />);

    expect(screen.getByText('No conditions recorded')).toBeTruthy();
    expect(screen.getByText('Unavailable')).toBeTruthy();
    expect(screen.getByText('Verification specification unavailable.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Refresh skill' }).disabled).toBe(true);
    expect(mocks.skillActions).toHaveBeenCalledWith({ skill, available: false, refresh });
  });
});
