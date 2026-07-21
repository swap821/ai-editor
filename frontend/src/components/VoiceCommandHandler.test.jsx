import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import VoiceCommandHandler from './VoiceCommandHandler';

describe('VoiceCommandHandler', () => {
  let mockSpeechRecognition;
  
  beforeEach(() => {
    mockSpeechRecognition = {
      start: vi.fn(),
      stop: vi.fn(),
      onresult: null,
      onerror: null
    };

    global.window.SpeechRecognition = vi.fn(function() { return mockSpeechRecognition; });
  });

  it('shows error if Web Speech API is missing', () => {
    delete global.window.SpeechRecognition;
    delete global.window.webkitSpeechRecognition;

    render(<VoiceCommandHandler isListening={true} />);
    expect(screen.getByTestId('voice-error')).toHaveTextContent(/not supported/i);
  });

  it('starts listening when isListening is true', () => {
    render(<VoiceCommandHandler isListening={true} />);
    expect(mockSpeechRecognition.start).toHaveBeenCalled();
    expect(screen.getByTestId('voice-listening-status')).toHaveTextContent('listening');
  });

  it('does not start when isListening is false', () => {
    render(<VoiceCommandHandler isListening={false} />);
    expect(mockSpeechRecognition.start).not.toHaveBeenCalled();
    expect(screen.getByTestId('voice-listening-status')).toHaveTextContent('idle');
  });

  it('calls onCommand when a transcript is received', () => {
    const onCommand = vi.fn();
    render(<VoiceCommandHandler isListening={true} onCommand={onCommand} />);
    
    // Simulate a speech result
    mockSpeechRecognition.onresult({
      results: [
        [
          { transcript: '  hello superbrain  ' }
        ]
      ]
    });

    expect(onCommand).toHaveBeenCalledWith('hello superbrain');
  });
});
