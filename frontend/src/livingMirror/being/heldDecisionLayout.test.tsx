import { readFileSync } from 'node:fs';
import type { CSSProperties } from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';

afterEach(() => { cleanup(); document.querySelectorAll('[data-held-layout-style]').forEach(style => style.remove()); });

// JSDOM has no viewport media layout. Apply the actual stylesheet's matching
// top-level media branch just as the existing fixture focus witness does.
// This proves selector/cascade ownership, not painted/native phone bounds.
it.each(['(min-width: 768px)', '(max-width: 767px)'])(
  'keeps an actionless resting Stop notice in the conversation decision allocation at %s', media => {
    const sheet = document.createElement('style'); sheet.dataset.heldLayoutStyle = '';
    sheet.textContent = readFileSync('src/workbench/GagosChrome.css', 'utf8')
      + readFileSync('src/livingMirror/livingMirror.css', 'utf8'); document.head.append(sheet);
    const matching = document.createElement('style'); matching.dataset.heldLayoutStyle = '';
    matching.textContent = [...(sheet.sheet?.cssRules ?? [])]
      .filter((rule): rule is CSSMediaRule => rule.type === CSSRule.MEDIA_RULE && (rule as CSSMediaRule).conditionText === media)
      .flatMap(rule => [...rule.cssRules].map(child => child.cssText)).join('\n');
    document.head.append(matching);
    const view = render(<div className="lm-app" data-working="false" style={{
      '--lm-workspace-dock-clearance': '117px', '--lm-conversation-rail': '448px',
    } as CSSProperties}>
      <div className="gagos-chrome" data-approval-pending="false">
        <div className="gagos-approval-hold approval-panel" role="alert">Emergency stop is engaged. This permission request is being held.</div>
      </div>
    </div>);
    const notice = view.getByRole('alert');
    const hostStyle = getComputedStyle(view.container.querySelector('.lm-app')!);
    expect.soft(hostStyle.getPropertyValue('--lm-conversation-dock'), 'the reservation must come from the real matching producer, not this witness').toContain('--lm-workspace-dock-clearance');
    if (media === '(max-width: 767px)') {
      expect.soft(hostStyle.getPropertyValue('--lm-conversation-permission-presence'), 'the narrow maximum must have its body reservation dependency').not.toBe('');
    }
    // This CSSOM does not substitute custom properties. Assert which measured
    // owner the matched cascade selects; native bounds are checked separately.
    expect(getComputedStyle(notice).bottom, 'Stop must use the conversation dock, not the unrelated work-side fallback').toContain('--lm-conversation-dock');
    expect(notice.getAttribute('role')).toBe('alert');
    expect(view.queryByRole('alertdialog')).toBeNull();
    expect(view.queryByRole('button')).toBeNull();
    expect(view.container.querySelector('.gagos-chrome')?.getAttribute('data-approval-pending')).toBe('false');
  },
);
