import { describe, it, expect } from 'vitest';
import { parseSseBuffer } from './sse';

describe('parseSseBuffer', () => {
  it('parses complete frames into event + data', () => {
    const buf =
      'event: step\ndata: {"tool":"read_file"}\n\n' +
      'event: text_chunk\ndata: {"text":"hi"}\n\n';
    const { frames, rest } = parseSseBuffer(buf);
    expect(rest).toBe('');
    expect(frames).toEqual([
      { event: 'step', data: '{"tool":"read_file"}' },
      { event: 'text_chunk', data: '{"text":"hi"}' },
    ]);
  });

  it('carries an incomplete trailing frame in rest', () => {
    const buf = 'event: code\ndata: {"code":"x"}\n\nevent: done\ndata: {}';
    const { frames, rest } = parseSseBuffer(buf);
    expect(frames).toEqual([{ event: 'code', data: '{"code":"x"}' }]);
    expect(rest).toBe('event: done\ndata: {}');
  });

  it('recognises the human_required (approval) frame', () => {
    const { frames } = parseSseBuffer(
      'event: human_required\ndata: {"requiresApproval":true}\n\n'
    );
    expect(frames[0].event).toBe('human_required');
  });

  it('skips a frame that has no data line', () => {
    const { frames } = parseSseBuffer('event: ping\n\nevent: done\ndata: {}\n\n');
    expect(frames).toEqual([{ event: 'done', data: '{}' }]);
  });
});
