import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import './PulseShader'; // Ensure the shader material is registered

const ANTERIOR_SIGN = 1;
export const COUNCIL_NODES = [
  { caste: 'builder', position: new THREE.Vector3(0, 0.26, 0.48 * ANTERIOR_SIGN), color: '#19d4f0' }, // Frontal/Causal
  { caste: 'scout', position: new THREE.Vector3(0.05, 0.31, -0.38 * ANTERIOR_SIGN), color: '#36f07a' }, // Occipital/Signal
  { caste: 'reviewer', position: new THREE.Vector3(0.34, 0.16, 0.11 * ANTERIOR_SIGN), color: '#ff7a26' }, // Temporal/Archive
  { caste: 'planner', position: new THREE.Vector3(0, 0.61, 0.11), color: '#9b3bff' }, // Parietal/Lattice
  { caste: 'synthesizer', position: new THREE.Vector3(-0.34, 0.16, 0.11 * ANTERIOR_SIGN), color: '#e62bd4' }, // Temporal Left
  { caste: 'soldier', position: new THREE.Vector3(0, -0.1, -0.2 * ANTERIOR_SIGN), color: '#ff3b28' }, // Cerebellum
];

export default function NerveMesh({ activeStates }: { activeStates: Float32Array }) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const materialRef = useRef<any>(null);

  useEffect(() => {
    if (!meshRef.current) return;
    const mesh = meshRef.current;
    const dummy = new THREE.Object3D();
    const color = new THREE.Color();
    
    // Set static positions and base colors once
    for (let i = 0; i < COUNCIL_NODES.length; i++) {
      const node = COUNCIL_NODES[i];
      dummy.position.copy(node.position);
      // We start with a neutral scale of 1, the shader multiplies it by 1.5/0.5
      dummy.scale.set(1, 1, 1);
      dummy.updateMatrix();
      
      mesh.setMatrixAt(i, dummy.matrix);
      color.set(node.color);
      mesh.setColorAt(i, color);
    }
    
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, []);

  useFrame((state) => {
    if (materialRef.current) {
      materialRef.current.uTime = state.clock.elapsedTime;
    }
  });

  const geometry = useMemo(() => {
    const geo = new THREE.SphereGeometry(0.06, 16, 16);
    return geo;
  }, []);

  return (
    <instancedMesh 
      ref={meshRef}
      args={[geometry, undefined, COUNCIL_NODES.length]}
      frustumCulled={false}
    >
      <pulseMaterial
        ref={materialRef}
        transparent={true}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
      <instancedBufferAttribute
        attach="geometry-attributes-aActive"
        args={[activeStates, 1]}
        needsUpdate={true}
      />
    </instancedMesh>
  );
}
