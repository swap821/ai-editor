export type HistoryEvent = {
  id: number;
  type: string;
  summary: string;
  occurredAt: string | null;
  receivedAt: string;
  missionId?: string;
  workerId?: string;
};

export type HistoryExperience = 'guided' | 'expert';

export type HistoryPresentation = {
  label: string;
  message: string;
  occurredAt: string | null;
  receivedAt: string;
  technical?: {
    type: string;
    summary: string;
    missionId?: string;
    workerId?: string;
  };
};

function guidedCopy(type: string): Pick<HistoryPresentation, 'label' | 'message'> {
  if (type === 'approval.required' || type === 'human_required') {
    return { label: 'Permission needed', message: 'GAGOS is waiting for your permission before it continues.' };
  }
  if (type === 'approval.resolved' || type === 'approval.decided') {
    return { label: 'Permission recorded', message: 'Your permission decision was recorded.' };
  }
  if (type.startsWith('worker.')) {
    return { label: 'Temporary work updated', message: 'Temporary work is being coordinated.' };
  }
  if (type.startsWith('mission.')) {
    return { label: 'Task updated', message: 'Your task changed state.' };
  }
  if (type === 'verify_result' || type.startsWith('verification.')) {
    return { label: 'Result check recorded', message: 'A result check was recorded.' };
  }
  if (type === 'security.refusal.recorded' || type.includes('injection')) {
    return { label: 'Action declined safely', message: 'GAGOS stopped at the permission boundary.' };
  }
  if (type.startsWith('governance.emergency_stop')) {
    return { label: 'System stopped', message: 'GAGOS stopped action safely.' };
  }
  if (type.startsWith('memory.')) {
    return { label: 'Learned context updated', message: 'Relevant learned context changed.' };
  }
  if (type.startsWith('route.')) {
    return { label: 'Path selected', message: 'A permitted path was selected.' };
  }
  if (type.includes('reflex')) {
    return { label: 'Verified routine reused', message: 'A verified routine was reused.' };
  }
  if (type.startsWith('turn.')) {
    return { label: 'Conversation updated', message: 'The conversation changed state.' };
  }
  return { label: 'System update', message: 'A system update was recorded.' };
}

export function presentHistoryEvent(event: HistoryEvent, experience: HistoryExperience): HistoryPresentation {
  const base = {
    ...guidedCopy(event.type),
    occurredAt: event.occurredAt,
    receivedAt: event.receivedAt,
  };
  if (experience === 'guided') return base;
  return {
    occurredAt: event.occurredAt,
    receivedAt: event.receivedAt,
    label: event.type,
    message: event.summary,
    technical: {
      type: event.type,
      summary: event.summary,
      ...(event.missionId ? { missionId: event.missionId } : {}),
      ...(event.workerId ? { workerId: event.workerId } : {}),
    },
  };
}
