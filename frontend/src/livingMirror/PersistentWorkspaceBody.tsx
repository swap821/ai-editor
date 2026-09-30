import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { WorkspaceActivityContext } from './WorkspaceActivityContext';

/** The tab store owns lifetime; this remembers only whether its view was visited.
 *  Never-selected views do no work. Open visited views keep their DOM/editor
 *  instances; closing/removing a record releases them normally through React. */
export function PersistentWorkspaceBody({ selected, visible, children, className = '' }: {
  selected: boolean;
  visible: boolean;
  children: ReactNode;
  className?: string;
}) {
  const [visited, setVisited] = useState(selected);
  if (selected && !visited) setVisited(true);
  const body = useRef<HTMLDivElement>(null);
  const scroll = useRef({ top: 0, left: 0 });
  useLayoutEffect(() => {
    if (!visible || !body.current) return;
    body.current.scrollTop = scroll.current.top;
    body.current.scrollLeft = scroll.current.left;
  }, [visible]);
  if (!selected && !visited) return null;
  return <div
    ref={body}
    className={`lm-surface__body ${className}`.trim()}
    hidden={!selected}
    inert={!visible}
    onScroll={(event) => {
      // Display:none can report zero dimensions. Do not overwrite the last
      // visible position with a browser-generated hidden-state scroll event.
      if (visible) scroll.current = { top: event.currentTarget.scrollTop, left: event.currentTarget.scrollLeft };
    }}
  >
    <WorkspaceActivityContext.Provider value={visible}>{children}</WorkspaceActivityContext.Provider>
  </div>;
}
