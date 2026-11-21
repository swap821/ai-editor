import { readFileSync } from 'node:fs';
import { afterEach, expect, it, vi } from 'vitest';

type TextBuilderConfig = { useWorker: boolean; defaultFontURL: string };

const { configureTextBuilder } = vi.hoisted(() => ({
  configureTextBuilder: vi.fn(),
}));

vi.mock('troika-three-text', () => ({ configureTextBuilder }));

afterEach(() => {
  vi.resetModules();
  configureTextBuilder.mockClear();
});

it('configures troika with useWorker false and a same-origin default font URL at /fonts/fixture-outfit.ttf', async () => {
  await import('./troikaConfig');

  expect(configureTextBuilder).toHaveBeenCalledTimes(1);
  const [config] = configureTextBuilder.mock.calls[0] as [TextBuilderConfig];
  expect(config.useWorker).toBe(false);

  const url = new URL(config.defaultFontURL);
  expect(url.origin).toBe(window.location.origin);
  expect(url.pathname.split('/')).toEqual(['', 'fonts', 'fixture-outfit.ttf']);
});

it('ships the fixture-outfit.ttf font file in public/fonts with more than 1000 characters', () => {
  const text = readFileSync(['public', 'fonts', 'fixture-outfit.ttf'].join('/'), 'utf8');

  expect(text.length).toBeGreaterThan(1000);
});
