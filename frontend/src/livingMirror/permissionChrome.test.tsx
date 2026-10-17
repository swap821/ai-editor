import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import GuidedApprovalPanel from './GuidedApprovalPanel';
import ApprovalPanel from '../superbrain/components/ui/ApprovalPanel';
import type { PendingApproval } from '../superbrain/lib/aiosAdapter';

describe('permission reading ownership', () => {
  it.each([['Guided', GuidedApprovalPanel], ['Expert', ApprovalPanel]] as const)(
    'keeps long %s request details in the scrollable proposal, not fixed action chrome', (_mode, Component) => {
      const filepath = 'fixture/a-very-long-request-owned-location-that-must-remain-fully-readable-without-erasing-the-body.integration.test.tsx';
      const pending: PendingApproval = {
        token: 'inert-layout-example', prompt: '', kind: 'create', filepath,
        summary: 'A long server-owned description that must not squeeze the decision buttons or erase the body band. '.repeat(5),
        explanation: '', diff: '--- /dev/null\n+++ ' + filepath + '\n+Example', content: '', command: '', url: '',
      };
      // Real markup with no effect/transport execution. Actual browser CSS
      // independently verifies its44px proposal viewport and stable actions.
      const host = document.createElement('div');
      host.innerHTML = renderToStaticMarkup(createElement(Component, { pending, onSettled: () => {} }));
      const body = host.querySelector('.approval-body')!;
      const summary = host.querySelector('.approval-summary')!;
      expect(body.contains(summary)).toBe(true);
      expect(body.textContent).toContain(filepath);
      expect(body.textContent).toContain(pending.summary);
      expect(body.contains(host.querySelector('.approval-actions'))).toBe(false);
    },
  );
});
