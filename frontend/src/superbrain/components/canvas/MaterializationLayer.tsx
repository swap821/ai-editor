import { useEffect } from 'react';
import { getLastEmittedCode } from '@/lib/aiosAdapter';
import { subscribeCognition } from '@/lib/cognitionBus';
import {
  getFirstMaterializedTab,
  spawnMaterializedTab,
  updateMaterializedTab,
  useTabStore,
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
  return {
    code: String(content.code ?? ''),
    language: String(content.language ?? 'text'),
    filepath: String(content.filepath ?? 'materialized.txt'),
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
        const current = getFirstMaterializedTab();
        if (!current) {
          spawnMaterializedTab(content);
          return;
        }
        updateMaterializedTab(current.id, { content });
      }),
    [],
  );

  useEffect(() => {
    if (process.env.NODE_ENV === 'production') return undefined;
    const host = window as typeof window & {
      __materializeTab?: (content?: Partial<MaterializedTabContent>) => void;
    };
    host.__materializeTab = (content = {}) => {
      const next = normalizeContent({
        ...DEV_STUB_CONTENT,
        ...content,
      });
      if (!next) return;
      const current = getFirstMaterializedTab();
      if (!current) {
        spawnMaterializedTab(next);
        return;
      }
      updateMaterializedTab(current.id, { content: next });
    };
    return () => {
      delete host.__materializeTab;
    };
  }, []);

  if (tabs.length === 0) return null;

  return (
    <>
      {tabs.map((tab) => (
        <MaterializedTab key={tab.id} tab={tab} reducedMotion={reducedMotion} />
      ))}
    </>
  );
}
