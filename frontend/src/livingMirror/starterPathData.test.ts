import { describe, expect, it } from 'vitest';
import { STARTER_PATHS } from './starterPathData';

describe('STARTER_PATHS', () => {
  it('provides the three starter paths in their intended order', () => {
    expect(STARTER_PATHS.map(({ id, title }) => ({ id, title }))).toEqual([
      { id: 'understand', title: 'Ask & understand' },
      { id: 'make', title: 'Make something' },
      { id: 'guide', title: 'Guide me' },
    ]);
  });

  it('provides a description and prompt for each path', () => {
    expect(STARTER_PATHS.map(({ description, prompt }) => ({ description, prompt }))).toEqual([
      {
        description: 'Explain something, compare options, or help me understand this project.',
        prompt: 'What can you help me with?',
      },
      {
        description: 'Create or improve something useful.',
        prompt: 'Create a simple plan for this project',
      },
      {
        description: 'Help me finish a task one safe step at a time.',
        prompt: 'Guide me through one safe first task',
      },
    ]);
  });
});
