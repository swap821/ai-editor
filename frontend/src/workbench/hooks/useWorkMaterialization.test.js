import { describe, expect, it } from 'vitest';
import { workFilepath, extractStreamingCode } from './useWorkMaterialization';

describe('workFilepath', () => {
  it('uses an explicit filename from the prompt, lowercased', () => {
    expect(workFilepath('save it to Main.PY please', 'javascript')).toBe('main.py');
  });

  it('names the file after the requested function and maps the language to an extension', () => {
    expect(workFilepath('function fibonacci', 'python')).toBe('fibonacci.py');
    expect(workFilepath('class fibonacci', 'rust')).toBe('fibonacci.rs');
  });

  it('detects the language from the prompt and builds a slug from the remaining words', () => {
    expect(workFilepath('write a python function named fibonacci')).toBe('fibonacci.py');
  });

  it('falls back to work.txt when nothing meaningful is in the prompt', () => {
    expect(workFilepath('please do it', '')).toBe('work.txt');
    expect(workFilepath(null, '')).toBe('work.txt');
  });
});

describe('extractStreamingCode', () => {
  it('returns empty text code when there is no fence yet', () => {
    expect(extractStreamingCode('just some prose')).toEqual({ code: '', language: 'text' });
    expect(extractStreamingCode(undefined)).toEqual({ code: '', language: 'text' });
  });

  it('returns the partial code of a fence that is still open', () => {
    expect(extractStreamingCode('intro\n```python\nprint(1)')).toEqual({
      code: 'print(1)',
      language: 'python',
    });
  });

  it('stops at the closing fence and ignores trailing text', () => {
    expect(extractStreamingCode('```js\nlet a = 1;\n```\ntrailing words')).toEqual({
      code: 'let a = 1;\n',
      language: 'js',
    });
  });

  it('defaults the language to text for a bare fence', () => {
    expect(extractStreamingCode('```\nx = 2')).toEqual({ code: 'x = 2', language: 'text' });
  });
});
