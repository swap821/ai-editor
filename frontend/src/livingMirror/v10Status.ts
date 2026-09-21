import { isRecord } from './contracts';

export interface V10Finding {
  kind: string | null;
  severity: string | null;
  targetId: string | null;
  recommendation: string | null;
}

export interface V10Scan {
  findingCount: number | null;
  cloudCalls: number | null;
  networkCalls: number | null;
  writesPerformed: boolean | null;
  topFindings: V10Finding[] | null;
}

export interface V10ScannerStatus {
  available: boolean | null;
  activation: string | null;
  localOnly: boolean | null;
  lastScan: V10Scan | null | undefined;
}

export type V10VultureStatus = V10ScannerStatus;

export interface V10EcosystemStatus {
  ecosystem: V10ScannerStatus | null;
  constitution: { casteCount: number | null; frozenCoreProtected: boolean | null } | null;
  symbolRepoMap: {
    activation: string | null;
    lastScan: { symbolCount: number | null; evidenceFileCount: number | null } | null | undefined;
  } | null;
  metaLoop: { safetyStatus: string | null; proposalCount: number | null } | null;
  councilMemory: { deliberationCount: number | null } | null;
}

const optionalText = (value: unknown): string | null => typeof value === 'string' && value.trim() ? value : null;
const optionalBoolean = (value: unknown): boolean | null => typeof value === 'boolean' ? value : null;
const optionalCount = (value: unknown): number | null => (
  typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null
);

function parseScan(value: unknown, label: string): V10Scan | null {
  if (value === null) return null;
  if (!isRecord(value)) throw new Error(`Unsupported ${label} scan response.`);
  const rawFindings = value.topFindings;
  let topFindings: V10Finding[] | null = null;
  if (Array.isArray(rawFindings)) {
    if (!rawFindings.every(isRecord)) throw new Error(`Unsupported ${label} finding response.`);
    topFindings = rawFindings.map((finding) => ({
      kind: optionalText(finding.kind),
      severity: optionalText(finding.severity),
      targetId: optionalText(finding.targetId),
      recommendation: optionalText(finding.recommendation),
    }));
  }
  return {
    findingCount: optionalCount(value.findingCount),
    cloudCalls: optionalCount(value.cloudCalls),
    networkCalls: optionalCount(value.networkCalls),
    writesPerformed: optionalBoolean(value.writesPerformed),
    topFindings,
  };
}

export function parseV10Scanner(value: unknown, label: string): V10ScannerStatus | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) throw new Error(`Unsupported ${label} status response.`);
  return {
    available: optionalBoolean(value.available),
    activation: optionalText(value.activation),
    localOnly: optionalBoolean(value.localOnly),
    lastScan: Object.prototype.hasOwnProperty.call(value, 'lastScan')
      ? parseScan(value.lastScan, label)
      : undefined,
  };
}

function parseSymbolRepoMap(value: unknown) {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) throw new Error('Unsupported symbol RepoMap response.');
  const rawScan = value.lastScan;
  let lastScan: { symbolCount: number | null; evidenceFileCount: number | null } | null | undefined;
  if (Object.prototype.hasOwnProperty.call(value, 'lastScan')) {
    if (rawScan === null) lastScan = null;
    else if (isRecord(rawScan)) {
      lastScan = {
        symbolCount: optionalCount(rawScan.symbolCount),
        evidenceFileCount: optionalCount(rawScan.evidenceFileCount),
      };
    } else throw new Error('Unsupported symbol RepoMap scan response.');
  }
  return { activation: optionalText(value.activation), lastScan };
}

export function parseV10VultureStatus(value: unknown): V10VultureStatus | null {
  if (!isRecord(value)) throw new Error('Unsupported v10 status response.');
  return parseV10Scanner(value.vulture, 'vulture');
}

export function parseV10EcosystemStatus(value: unknown): V10EcosystemStatus {
  if (!isRecord(value)) throw new Error('Unsupported v10 status response.');
  const constitution = isRecord(value.constitution)
    ? { casteCount: optionalCount(value.constitution.casteCount), frozenCoreProtected: optionalBoolean(value.constitution.frozenCoreProtected) }
    : null;
  const metaLoop = isRecord(value.metaLoop)
    ? { safetyStatus: optionalText(value.metaLoop.safetyStatus), proposalCount: optionalCount(value.metaLoop.proposalCount) }
    : null;
  const councilMemory = isRecord(value.councilMemory)
    ? { deliberationCount: optionalCount(value.councilMemory.deliberationCount) }
    : null;
  return {
    ecosystem: parseV10Scanner(value.ecosystem, 'ecosystem'),
    constitution,
    symbolRepoMap: parseSymbolRepoMap(value.symbolRepoMap),
    metaLoop,
    councilMemory,
  };
}
