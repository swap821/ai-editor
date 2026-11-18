import * as THREE from 'three';

const ANTERIOR_SIGN = 1;
export const COUNCIL_NODES = [
  { caste: 'builder', position: new THREE.Vector3(0, 0.26, 0.48 * ANTERIOR_SIGN), color: '#19d4f0' }, // Frontal/Causal
  { caste: 'scout', position: new THREE.Vector3(0.05, 0.31, -0.38 * ANTERIOR_SIGN), color: '#36f07a' }, // Occipital/Signal
  { caste: 'reviewer', position: new THREE.Vector3(0.34, 0.16, 0.11 * ANTERIOR_SIGN), color: '#ff7a26' }, // Temporal/Archive
  { caste: 'planner', position: new THREE.Vector3(0, 0.61, 0.11), color: '#9b3bff' }, // Parietal/Lattice
  { caste: 'synthesizer', position: new THREE.Vector3(-0.34, 0.16, 0.11 * ANTERIOR_SIGN), color: '#e62bd4' }, // Temporal Left
  { caste: 'soldier', position: new THREE.Vector3(0, -0.1, -0.2 * ANTERIOR_SIGN), color: '#ff3b28' }, // Cerebellum
];
