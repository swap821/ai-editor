/**
 * Utils barrel export — central security utilities.
 *
 * All sanitization functions live in sanitizeHtml.js and are re-exported here
 * for clean imports: import { sanitizeHtml, escapeHtml, sanitizeToText } from '../utils';
 */

export {
  sanitizeHtml,
  escapeHtml,
  sanitizeToText,
} from './sanitizeHtml';
