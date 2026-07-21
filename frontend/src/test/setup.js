// Vitest global setup: register @testing-library/jest-dom matchers
// (toBeInTheDocument, etc.) on every test file.
import '@testing-library/jest-dom';

// Monaco editor relies on this DOM API which jsdom doesn't provide
if (typeof document !== 'undefined') {
  document.queryCommandSupported = () => false;
}
