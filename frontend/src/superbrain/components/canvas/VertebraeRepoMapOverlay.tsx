import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { SEGMENT_ANCHORS, SEGMENT_COUNT } from '@/lib/spineAnatomy';
import { getRepoMapState, subscribeRepoMap, type RepoMapNode } from '@/lib/repoMapStore';

const STATUS_COLORS: Record<string, THREE.Color> = {
  editing: new THREE.Color('#19d4f0'),    // cyan
  verifying: new THREE.Color('#ff7a26'),  // burnt orange
  approved: new THREE.Color('#36f07a'),   // green
  failed: new THREE.Color('#ff3b28'),     // red
  idle: new THREE.Color('#6a35ff'),       // violet
};

export default function VertebraeRepoMapOverlay() {
  const [activeFiles, setActiveFiles] = useState<RepoMapNode[]>([]);
  const pointsRef = useRef<THREE.InstancedMesh>(null);
  
  useEffect(() => {
    return subscribeRepoMap((state) => {
      setActiveFiles(state.activeFiles);
    });
  }, []);

  // We have up to SEGMENT_COUNT anchors (12)
  const count = Math.min(activeFiles.length, SEGMENT_COUNT);

  // Re-compute instance matrices and colors whenever files change
  useEffect(() => {
    if (!pointsRef.current || count === 0) return;
    
    const mesh = pointsRef.current;
    const dummy = new THREE.Object3D();
    const color = new THREE.Color();
    
    for (let i = 0; i < SEGMENT_COUNT; i++) {
      if (i < count) {
        const file = activeFiles[i];
        const anchor = SEGMENT_ANCHORS[i];
        
        // Scale based on error count
        const scale = 1.0 + Math.min(file.errorCount * 0.2, 1.5);
        
        dummy.position.copy(anchor);
        // Offset slightly out from the cord
        dummy.position.z += 0.35;
        dummy.scale.set(scale, scale, scale);
        dummy.updateMatrix();
        
        mesh.setMatrixAt(i, dummy.matrix);
        
        const baseColor = STATUS_COLORS[file.status] || STATUS_COLORS['idle'];
        color.copy(baseColor);
        if (file.errorCount > 0) {
          color.lerp(STATUS_COLORS['failed'], 0.5); // Blend toward red if errors exist
        }
        mesh.setColorAt(i, color);
      } else {
        // Hide unused instances by scaling to 0
        dummy.scale.set(0, 0, 0);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      }
    }
    
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [activeFiles, count]);

  // Pulse effect based on error count
  useFrame((state) => {
    if (!pointsRef.current || count === 0) return;
    const mesh = pointsRef.current;
    const time = state.clock.elapsedTime;
    const dummy = new THREE.Object3D();
    let needsUpdate = false;

    for (let i = 0; i < count; i++) {
      const file = activeFiles[i];
      if (file.errorCount > 0) {
        const anchor = SEGMENT_ANCHORS[i];
        const baseScale = 1.0 + Math.min(file.errorCount * 0.2, 1.5);
        const pulse = 1.0 + Math.sin(time * 5 + i) * 0.2;
        const scale = baseScale * pulse;
        
        dummy.position.copy(anchor);
        dummy.position.z += 0.35;
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

  const geometry = useMemo(() => new THREE.SphereGeometry(0.04, 16, 16), []);
  const material = useMemo(() => new THREE.MeshBasicMaterial({ 
    color: 0xffffff,
    transparent: true,
    opacity: 0.8,
    blending: THREE.AdditiveBlending
  }), []);

  if (count === 0) return null;

  return (
    <instancedMesh 
      ref={pointsRef}
      args={[geometry, material, SEGMENT_COUNT]}
      frustumCulled={false}
    />
  );
}
