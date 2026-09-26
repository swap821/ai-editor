export interface WorkerSeatAssignment {
  workerId: string;
  seat: number;
}

/** Keep live workers attached to their last seat; give arrivals the lowest free seat. */
export function reconcileWorkerSeats(
  previous: readonly WorkerSeatAssignment[],
  workerIds: readonly string[],
  capacity = 8,
): WorkerSeatAssignment[] {
  const limit = Math.max(0, Math.floor(capacity));
  if (limit === 0) return [];

  const requested = [...new Set(workerIds.filter((workerId) => workerId.trim().length > 0))].slice(0, limit);
  const requestedSet = new Set(requested);
  const assigned = new Map<string, number>();
  const occupied = new Set<number>();

  for (const assignment of previous) {
    const { workerId, seat } = assignment;
    if (!requestedSet.has(workerId) || assigned.has(workerId)) continue;
    if (!Number.isInteger(seat) || seat < 0 || seat >= limit || occupied.has(seat)) continue;
    assigned.set(workerId, seat);
    occupied.add(seat);
  }

  for (const workerId of requested) {
    if (assigned.has(workerId)) continue;
    let seat = 0;
    while (occupied.has(seat) && seat < limit) seat += 1;
    if (seat >= limit) break;
    assigned.set(workerId, seat);
    occupied.add(seat);
  }

  return requested.flatMap((workerId) => {
    const seat = assigned.get(workerId);
    return seat === undefined ? [] : [{ workerId, seat }];
  });
}
