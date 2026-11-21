import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { COUNCIL_NODES } from './councilNodes';

describe('COUNCIL_NODES', () => {
  it('lists the six castes in a fixed order', () => {
    expect(COUNCIL_NODES.map((n) => n.caste)).toEqual([
      'builder',
      'scout',
      'reviewer',
      'planner',
      'synthesizer',
      'soldier',
    ]);
  });

  it('gives every node a THREE.Vector3 position', () => {
    for (const node of COUNCIL_NODES) {
      expect(node.position).toBeInstanceOf(THREE.Vector3);
    }
  });

  it('assigns each caste its exact color', () => {
    const colors = Object.fromEntries(COUNCIL_NODES.map((n) => [n.caste, n.color]));
    expect(colors).toEqual({
      builder: '#19d4f0',
      scout: '#36f07a',
      reviewer: '#ff7a26',
      planner: '#9b3bff',
      synthesizer: '#e62bd4',
      soldier: '#ff3b28',
    });
  });

  it('places each caste at its exact brain-region position', () => {
    const positions = Object.fromEntries(
      COUNCIL_NODES.map((n) => [n.caste, [n.position.x, n.position.y, n.position.z]]),
    );
    expect(positions).toEqual({
      builder: [0, 0.26, 0.48],
      scout: [0.05, 0.31, -0.38],
      reviewer: [0.34, 0.16, 0.11],
      planner: [0, 0.61, 0.11],
      synthesizer: [-0.34, 0.16, 0.11],
      soldier: [0, -0.1, -0.2],
    });
  });

  it('mirrors the temporal nodes across the midline', () => {
    const reviewer = COUNCIL_NODES.find((n) => n.caste === 'reviewer');
    const synthesizer = COUNCIL_NODES.find((n) => n.caste === 'synthesizer');
    expect(reviewer).toBeDefined();
    expect(synthesizer).toBeDefined();
    expect(reviewer?.position.x).toBe(-(synthesizer?.position.x ?? 0));
    expect(reviewer?.position.y).toBe(synthesizer?.position.y);
    expect(reviewer?.position.z).toBe(synthesizer?.position.z);
  });
});
