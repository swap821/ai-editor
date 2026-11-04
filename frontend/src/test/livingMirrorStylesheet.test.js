import { describe, it, expect, vi, beforeEach } from 'vitest';

const { readFileSyncMock } = vi.hoisted(() => ({
  readFileSyncMock: vi.fn(),
}));

vi.mock('node:fs', () => ({
  readFileSync: readFileSyncMock,
  default: { readFileSync: readFileSyncMock },
}));

import { readLivingMirrorStylesheet } from './livingMirrorStylesheet';

describe('readLivingMirrorStylesheet', () => {
  beforeEach(() => {
    readFileSyncMock.mockReset();
  });

  it('returns the stylesheet text read from disk', () => {
    const css = '.living-mirror { color: red; }';
    readFileSyncMock.mockReturnValue(css);

    expect(readLivingMirrorStylesheet()).toBe(css);
    expect(readFileSyncMock).toHaveBeenCalledTimes(1);
  });

  it('reads a src-relative path as utf8 text', () => {
    readFileSyncMock.mockReturnValue('');

    readLivingMirrorStylesheet();

    expect(readFileSyncMock).toHaveBeenCalledWith(
      expect.stringMatching(/^src/),
      'utf8',
    );
  });

  it('propagates read failures instead of swallowing them', () => {
    readFileSyncMock.mockImplementation(() => {
      throw new Error('ENOENT: no such file');
    });

    expect(() => readLivingMirrorStylesheet()).toThrow('ENOENT: no such file');
  });
});
