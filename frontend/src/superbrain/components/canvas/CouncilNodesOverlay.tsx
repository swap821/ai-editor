import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { getSwarmHUDState, subscribeSwarmHUD } from '@/lib/swarmHUDStore';

// Anatomy coordinates (approximate surface points on the brain GLB)
const ANTERIOR_SIGN = 1;
const COUNCIL_NODES = [
  { caste: 'builder', position: new THREE.Vector3(0, 0.26, 0.48 * ANTERIOR_SIGN), color: '#19d4f0' }, // Frontal/Causal
  { caste: 'scout', position: new THREE.Vector3(0.05, 0.31, -0.38 * ANTERIOR_SIGN), color: '#36f07a' }, // Occipital/Signal
  { caste: 'reviewer', position: new THREE.Vector3(0.34, 0.16, 0.11 * ANTERIOR_SIGN), color: '#ff7a26' }, // Temporal/Archive
  { caste: 'planner', position: new THREE.Vector3(0, 0.61, 0.11), color: '#9b3bff' }, // Parietal/Lattice
  { caste: 'synthesizer', position: new THREE.Vector3(-0.34, 0.16, 0.11 * ANTERIOR_SIGN), color: '#e62bd4' }, // Temporal Left
  { caste: 'soldier', position: new THREE.Vector3(0, -0.1, -0.2 * ANTERIOR_SIGN), color: '#ff3b28' }, // Cerebellum
];

export default function CouncilNodesOverlay() {
  const [activeCastes, setActiveCastes] = useState<string[]>([]);
  const meshRef = useRef<THREE.InstancedMesh>(null);

  useEffect(() => {
    return subscribeSwarmHUD((state) => {
      // Convert to lowercase to match our static array
      setActiveCastes(state.activeCastes.map(c => c.toLowerCase()));
    });
  }, []);

  useEffect(() => {
    if (!meshRef.current) return;
    
    const mesh = meshRef.current;
    const dummy = new THREE.Object3D();
    const color = new THREE.Color();
    
    for (let i = 0; i < COUNCIL_NODES.length; i++) {
      const node = COUNCIL_NODES[i];
      const isActive = activeCastes.some(c => c.includes(node.caste));
      
      dummy.position.copy(node.position);
      // Base scale, will be animated
      const scale = isActive ? 1.5 : 0.5;
      dummy.scale.set(scale, scale, scale);
      dummy.updateMatrix();
      
      mesh.setMatrixAt(i, dummy.matrix);
      
      color.set(node.color);
      if (!isActive) {
        color.multiplyScalar(0.2); // Dim when inactive
      }
      mesh.setColorAt(i, color);
    }
    
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [activeCastes]);

  useFrame((state) => {
    if (!meshRef.current) return;
    const mesh = meshRef.current;
    const time = state.clock.elapsedTime;
    const dummy = new THREE.Object3D();
    let needsUpdate = false;

    for (let i = 0; i < COUNCIL_NODES.length; i++) {
      const node = COUNCIL_NODES[i];
      const isActive = activeCastes.some(c => c.includes(node.caste));
      
      if (isActive) {
        const pulse = 1.0 + Math.sin(time * 6 + i) * 0.3;
        const scale = 1.5 * pulse;
        
        dummy.position.copy(node.position);
        dummy.scale.set(scale, scale, scale);
        dummy.updateMatrix();
        
        mesh.setMatrixAt(i, dummy.matrix);
        needsUpdate = true;
      }
    }
    
    if (needsUpdate) {
      mesh.instanceMatrix.needsUpdate = true;
    }
  });

  const geometry = useMemo(() => new THREE.SphereGeometry(0.06, 16, 16), []);
  const material = useMemo(() => new THREE.MeshBasicMaterial({ 
    color: 0xffffff,
    transparent: true,
    opacity: 0.9,
    blending: THREE.AdditiveBlending
  }), []);

  return (
    <instancedMesh 
      ref={meshRef}
      args={[geometry, material, COUNCIL_NODES.length]}
      frustumCulled={false}
    />
  );
}
