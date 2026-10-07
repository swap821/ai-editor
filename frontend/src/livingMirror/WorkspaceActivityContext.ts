import { createContext, useContext } from 'react';

/** Presentation visibility only; never grants authority or changes tab state. */
export const WorkspaceActivityContext = createContext(true);
export const useWorkspaceActive = () => useContext(WorkspaceActivityContext);
