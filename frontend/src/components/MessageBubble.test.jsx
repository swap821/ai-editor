import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import MessageBubble from './MessageBubble';

describe('MessageBubble', () => {
  it('renders a user message', () => {
    render(<MessageBubble msg={{ sender: 'user', text: 'hello world' }} />);
    expect(screen.getByText('hello world')).toBeInTheDocument();
  });

  it('renders an AI text answer', () => {
    render(<MessageBubble msg={{ sender: 'ai', text: 'Here is the answer' }} />);
    expect(screen.getByText(/Here is the answer/)).toBeInTheDocument();
  });

  it('renders an agent tool-call step with its label + input', () => {
    render(
      <MessageBubble
        msg={{
          sender: 'ai',
          text: '',
          steps: [
            { type: 'tool_call', tool: 'read_file', input: { filepath: 'a.txt' }, id: 's1' },
          ],
        }}
      />
    );
    expect(screen.getByText(/Read file/)).toBeInTheDocument();
    expect(screen.getByText(/filepath: a\.txt/)).toBeInTheDocument();
  });
});
