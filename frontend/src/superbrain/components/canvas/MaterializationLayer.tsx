import { useEffect } from 'react';
import { getLastEmittedCode, subscribePendingApproval, type PendingApproval } from '@/lib/aiosAdapter';
import { subscribeCognition } from '@/lib/cognitionBus';
import {
  getApprovalSurfacePlacement,
  getContentSurfacePlacement,
  getInputSurfacePlacement,
} from '@/lib/materializedSurfaceAnchors';
import {
  beginRetractingMaterializedTab,
  getFirstMaterializedTab,
  showApprovalSurface,
  showContentSurface,
  upsertInputSurface,
  useTabStore,
  type MaterializedApprovalSurface,
  type MaterializedTabContent,
} from '@/lib/tabStore';
import MaterializedTab from './MaterializedTab';

const DEV_STUB_CONTENT: MaterializedTabContent = {
  code: "export function hello(name = 'AI-OS') {\n  return `Hello, ${name}`;\n}\n",
  language: 'javascript',
  filepath: 'hello.js',
};

function normalizeContent(content: MaterializedTabContent | null): MaterializedTabContent | null {
  if (!content) return null;
  const code = String(content.code ?? '');
  if (!code.trim()) return null;
  return {
    code,
    language: String(content.language ?? 'text'),
    filepath: String(content.filepath ?? 'materialized.txt'),
  };
}

function normalizeApproval(pending: PendingApproval | null): MaterializedApprovalSurface | null {
  if (!pending) return null;
  return {
    token: String(pending.token ?? ''),
    summary: String(pending.summary ?? 'Approval required'),
    explanation: String(pending.explanation ?? ''),
    diff: String(pending.diff ?? ''),
    command: String(pending.command ?? ''),
    kindLabel: String(pending.kind ?? 'other'),
    filepath: String(pending.filepath ?? ''),
    content: String(pending.content ?? ''),
  };
}

export default function MaterializationLayer({ reducedMotion }: { reducedMotion: boolean }) {
  const { tabs } = useTabStore();

  useEffect(
    () =>
      subscribeCognition((event) => {
        if (event.type !== 'knowledge-acquired' || event.label !== 'CODE EMITTED') return;
        const content = normalizeContent(getLastEmittedCode());
        if (!content) return;
        showContentSurface(content, getContentSurfacePlacement());
      }),
    [],
  );

  useEffect(
    () =>
      subscribePendingApproval((pending) => {
        const approval = normalizeApproval(pending);
        if (approval) {
          showApprovalSurface(approval, getApprovalSurfacePlacement());
          return;
        }
        const current = getFirstMaterializedTab();
        if (current?.kind === 'approval') {
          beginRetractingMaterializedTab(current.id);
        }
      }),
    [],
  );

  useEffect(() => {
    if (process.env.NODE_ENV === 'production') return undefined;
    const host = window as typeof window & {
      __materializeTab?: (content?: Partial<MaterializedTabContent>) => void;
      __materializeInput?: (text?: string) => void;
      __materializeApproval?: (partial?: Partial<MaterializedApprovalSurface>) => void;
    };
    host.__materializeTab = (content = {}) => {
      const next = normalizeContent({
        ...DEV_STUB_CONTENT,
        ...content,
      });
      if (!next) return;
      showContentSurface(next, getContentSurfacePlacement());
    };
    host.__materializeInput = (text = 'build a living input surface') => {
      upsertInputSurface(text, getInputSurfacePlacement());
    };
    host.__materializeApproval = (partial = {}) => {
      showApprovalSurface(
        {
          token: 'dev-approval',
          summary: 'Approval required to materialize demo.py',
          explanation: 'Dev-only approval surface for embodied review.',
          diff: '+export const demo = true;\n',
          command: '',
          kindLabel: 'create',
          filepath: 'demo.py',
          content: 'export const demo = true;\n',
          ...partial,
        },
        getApprovalSurfacePlacement(),
      );
    };
    return () => {
      delete host.__materializeTab;
      delete host.__materializeInput;
      delete host.__materializeApproval;
    };
  }, []);

  if (tabs.length === 0) return null;

  return (
    <>
      {tabs.filter((tab) => tab.kind !== 'input').map((tab) => (
        <MaterializedTab key={tab.id} tab={tab} reducedMotion={reducedMotion} />
      ))}
    </>
  );
}
