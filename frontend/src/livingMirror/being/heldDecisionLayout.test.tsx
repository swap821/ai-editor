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
    // jsdom 31 substitutes custom properties, as browsers do (jsdom 30 did not,
    // and this asserted the variable names). The witness sets only the measured
    // clearance, 117px: the dock is 117px only if the real matching producer
    // derived it from that clearance, since nothing else sets it.
    expect.soft(hostStyle.getPropertyValue('--lm-conversation-dock').trim(), 'the reservation must come from the real matching producer, not this witness').toBe('117px');
    if (media === '(max-width: 767px)') {
      expect.soft(hostStyle.getPropertyValue('--lm-conversation-permission-presence'), 'the narrow maximum must have its body reservation dependency').not.toBe('');
    }
    // The notice sits at the conversation dock (117px, from the clearance); the
    // work-side rules and the dock's own fallbacks (358px, 312px) give other
    // values. Native bounds are checked separately.
    expect(getComputedStyle(notice).bottom, 'Stop must use the conversation dock, not the unrelated work-side fallback').toBe('117px');
    expect(notice.getAttribute('role')).toBe('alert');
    expect(view.queryByRole('alertdialog')).toBeNull();
    expect(view.queryByRole('button')).toBeNull();
    expect(view.container.querySelector('.gagos-chrome')?.getAttribute('data-approval-pending')).toBe('false');
  },
);
