export const STARTER_PATHS = [
  {
    id: 'understand',
    title: 'Ask & understand',
    description: 'Explain something, compare options, or help me understand this project.',
    prompt: 'What can you help me with?',
  },
  {
    id: 'make',
    title: 'Make something',
    description: 'Create or improve something useful.',
    prompt: 'Create a simple plan for this project',
  },
  {
    id: 'guide',
    title: 'Guide me',
    description: 'Help me finish a task one safe step at a time.',
    prompt: 'Guide me through one safe first task',
  },
] as const;
