export const STARTER_PATHS = [
  {
    id: 'understand',
    title: 'Understand something',
    description: 'Ask a question and get a clear explanation before anything changes.',
    prompt: 'What can you help me with?',
  },
  {
    id: 'make',
    title: 'Make something useful',
    description: 'Ask for a small draft. GAGOS will show the plan and wait for approval.',
    prompt: 'Create a simple plan for this project',
  },
  {
    id: 'guide',
    title: 'Guide me step by step',
    description: 'Start with one safe task and learn the controls as you go.',
    prompt: 'Guide me through one safe first task',
  },
] as const;
