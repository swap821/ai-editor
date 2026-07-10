import { useEffect, useMemo, useState } from 'react';
import { getSwarmHUDState, subscribeSwarmHUD } from '@/lib/swarmHUDStore';
import NerveMesh, { COUNCIL_NODES } from './NerveMesh';

export default function DeliberationOverlay() {
  const [activeCastes, setActiveCastes] = useState<string[]>([]);

  useEffect(() => {
    // Initial state
    setActiveCastes(getSwarmHUDState().activeCastes.map(c => c.toLowerCase()));

    // Subscribe to future updates
    return subscribeSwarmHUD((state) => {
      setActiveCastes(state.activeCastes.map(c => c.toLowerCase()));
    });
  }, []);

  const activeStates = useMemo(() => {
    const arr = new Float32Array(COUNCIL_NODES.length);
    for (let i = 0; i < COUNCIL_NODES.length; i++) {
      const node = COUNCIL_NODES[i];
      const isActive = activeCastes.some(c => c.includes(node.caste));
      arr[i] = isActive ? 1.0 : 0.0;
    }
    return arr;
  }, [activeCastes]);

  return <NerveMesh activeStates={activeStates} />;
}
