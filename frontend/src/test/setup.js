// Vitest global setup: register @testing-library/jest-dom matchers
// (toBeInTheDocument, etc.) on every test file.
// The `/vitest` subpath is the entry point jest-dom documents for vitest;
// it registers the matchers AND is the declaration file that
// src/test/jest-dom.d.ts pulls in for the type side.
import '@testing-library/jest-dom/vitest';

// Monaco editor relies on this DOM API which jsdom doesn't provide
if (typeof document !== 'undefined') {
  document.queryCommandSupported = () => false;
}
