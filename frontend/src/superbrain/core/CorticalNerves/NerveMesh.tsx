import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import './PulseShader'; // Ensure the shader material is registered
import { COUNCIL_NODES } from './councilNodes';

export default function NerveMesh({ activeStates }: { activeStates: Float32Array }) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const materialRef = useRef<{ uTime: number }>(null);

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
