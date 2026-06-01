import { test } from 'node:test';
import assert from 'node:assert/strict';
import { filterSteps, gate, CONFIDENCE_THRESHOLD } from '../confidenceFilter.js';

test('threshold is 0.72', () => {
  assert.equal(CONFIDENCE_THRESHOLD, 0.72);
});

test('confidence 0.719 escalates to human', () => {
  const r = gate(0.719);
  assert.equal(r.passed, false);
});

test('confidence 0.720 passes the filter', () => {
  const r = gate(0.720);
  assert.equal(r.passed, true);
});

test('filterSteps partitions correctly', () => {
  const steps = [
    { step_id: '1', description: 'safe', confidence: 0.95 },
    { step_id: '2', description: 'risky', confidence: 0.5 },
    { step_id: '3', description: 'edge', confidence: 0.72 },
  ];
  const { approved, escalate } = filterSteps(steps);
  assert.equal(approved.length, 2);
  assert.equal(escalate.length, 1);
  assert.equal(escalate[0].step.step_id, '2');
});

test('missing confidence is treated as 0 (escalate)', () => {
  const { approved, escalate } = filterSteps([{ step_id: '1', description: 'x' }]);
  assert.equal(approved.length, 0);
  assert.equal(escalate.length, 1);
});
