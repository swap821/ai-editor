/**
 * sanitizeHtml — defence-in-depth HTML sanitization for ALL untrusted content.
 *
 * CRITICAL FIX C17: All LLM output, tool results, and SSE-received content MUST
 * pass through this sanitizer before DOM insertion. Prompt injection can cause
 * the LLM to emit malicious HTML/JS (e.g. <script>alert(document.cookie)</script>),
 * which would execute in the operator's browser as a stored/reflected XSS.
 *
 * This is a MINIMAL but EFFECTIVE sanitizer — it does NOT try to be a full
 * HTML parser.  It removes dangerous tags, strips ALL event handlers, blocks
 * javascript: URLs, and allows only a safe whitelist of formatting tags.
 *
 * For production systems requiring richer HTML support, replace with DOMPurify:
 *   npm install dompurify
 *   import DOMPurify from 'dompurify';
 *   export const sanitizeHtml = (dirty) => DOMPurify.sanitize(dirty, {
 *     ALLOWED_TAGS: ['b','i','em','strong','code','pre','a','br','p','ul','ol','li'],
 *     ALLOWED_ATTR: ['href','target','rel'],
 *   });
 */

/** Dangerous tags that must NEVER appear in output — removed entirely. */
const DANGEROUS_TAGS = [
  'script', 'style', 'iframe', 'object', 'embed', 'applet', 'form', 'input',
  'textarea', 'button', 'select', 'option', 'link', 'meta', 'base', 'frame',
  'frameset', 'marquee', 'blink', 'xml', 'xss', 'svg', 'math',
];

/** Dangerous tag pattern: matches opening <tag, closing </tag>, or <!directive>. */
function getDangerousTagPattern() {
  const tagList = DANGEROUS_TAGS.join('|');
  return new RegExp(
    `<\\/?\\s*(?:${tagList})\\b[^>]*>` +
    '|' +
    `<!(?:--)?\\s*(?:DOCTYPE|ENTITY|ATTLIST|ELEMENT)[^>]*>`,
    'gi',
  );
}

/** HTML event handler attributes: onerror, onclick, onload, etc. */
const EVENT_HANDLER_PATTERN =
  /\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|`[^`]*`|[^\s>]*)/gi;

/** javascript: and data: URL schemes in attributes. */
const DANGEROUS_URL_PATTERN =
  /\s+(?:href|src|action|background|formaction|poster|profile|xmlns)\s*=\s*["']?(?:javascript|data|vbscript):[^"'>\s]*/gi;

/** CSS expression() — IE-specific dynamic property (legacy but dangerous). */
const EXPRESSION_PATTERN = /expression\s*\(/gi;

/** Inline style with javascript or expression. */
const DANGEROUS_STYLE_PATTERN =
  /\s+style\s*=\s*["'][^"']*(?:javascript:|expression\s*\()[^""]*["']/gi;

/** Allowed safe HTML tags for formatting LLM output. */
const ALLOWED_TAGS = new Set([
  'b', 'i', 'em', 'strong', 'code', 'pre', 'a', 'br', 'p', 'ul', 'ol', 'li',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'hr', 'del', 'ins',
  'sub', 'sup', 'small', 'mark', 'abbr', 'cite', 'dfn', 'kbd', 'samp', 'var',
  'div', 'span', 'table', 'thead', 'tbody', 'tr', 'td', 'th',
]);

/** Parse and filter allowed tags — strip disallowed tags but keep their text. */
function filterAllowedTags(html) {
  return html.replace(/<\/?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>/g, (match, tagName) => {
    const lowerTag = tagName.toLowerCase();
    if (ALLOWED_TAGS.has(lowerTag)) {
      // Tag is allowed — but still sanitize its attributes for href
      if (lowerTag === 'a') {
        return sanitizeAnchorTag(match);
      }
      // For allowed non-anchor tags, strip all attributes except safe ones
      return match.replace(/\s+[a-zA-Z_:][-\w:.]*\s*=\s*["'][^"']*["']/g, (attr) => {
        const attrName = attr.split('=')[0].trim().toLowerCase();
        // Only allow class (for syntax highlighting) and safe data attrs
        if (attrName === 'class' || attrName.startsWith('data-')) {
          return attr;
        }
        return '';
      });
    }
    // Disallowed tag: strip it (remove from output entirely — content is lost,
    // which is the SAFER choice vs. keeping potentially malicious content)
    return '';
  });
}

/** Sanitize <a> tags: only allow http://, https://, mailto:, tel:, #anchor. */
function sanitizeAnchorTag(tagHtml) {
  const hrefMatch = tagHtml.match(/\s+href\s*=\s*["']([^"]*)["']/i);
  if (!hrefMatch) {
    // No href — safe, keep as-is (could be <a name="...">)
    return tagHtml;
  }
  const href = hrefMatch[1].trim();
  const isSafe =
    href.startsWith('http://') ||
    href.startsWith('https://') ||
    href.startsWith('mailto:') ||
    href.startsWith('tel:') ||
    href.startsWith('#') ||
    href.startsWith('/') ||
    /^[a-zA-Z0-9_-]+\.html?$/i.test(href);

  if (!isSafe) {
    // Unsafe href — strip the href attribute but keep tag
    return tagHtml.replace(/\s+href\s*=\s*["'][^"]*["']/gi, '');
  }

  // Safe href — ensure rel="noopener noreferrer" for external links
  const hasRel = /\s+rel\s*=/i.test(tagHtml);
  if (!hasRel && (href.startsWith('http://') || href.startsWith('https://'))) {
    return tagHtml.replace(/>\s*$/, ' rel="noopener noreferrer">');
  }
  return tagHtml;
}

/**
 * Sanitize untrusted HTML — removes dangerous content while preserving safe
 * formatting.  Apply to ALL LLM output, tool results, and SSE content.
 *
 * @param {string} dirty — raw untrusted input (may contain malicious HTML)
 * @returns {string} — sanitized safe HTML (or plain text if no safe HTML remains)
 */
export function sanitizeHtml(dirty) {
  if (!dirty || typeof dirty !== 'string') return '';

  let clean = dirty;

  // 1. Remove ALL <script> tags and their content entirely
  clean = clean.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script\s*>/gi, '');

  // 2. Remove other dangerous tags entirely
  clean = clean.replace(getDangerousTagPattern(), '');

  // 3. Strip ALL event handler attributes (onerror, onclick, onload, etc.)
  // Repeat until stable to prevent incomplete multi-character sanitization bypasses.
  let prev;
  do {
    prev = clean;
    clean = clean.replace(EVENT_HANDLER_PATTERN, '');
  } while (clean !== prev);

  // 4. Strip dangerous URL schemes in attributes
  clean = clean.replace(DANGEROUS_URL_PATTERN, '');

  // 5. Strip CSS expression() (IE legacy)
  clean = clean.replace(EXPRESSION_PATTERN, '');

  // 6. Strip dangerous inline styles
  clean = clean.replace(DANGEROUS_STYLE_PATTERN, '');

  // 7. Filter to allowed tag whitelist + sanitize attributes
  clean = filterAllowedTags(clean);

  // 8. Defense-in-depth: catch any remaining <script...> patterns
  clean = clean.replace(/<script\b[^>]*>/gi, '');
  clean = clean.replace(/<\/script\s*>/gi, '');

  // 9. Catch HTML comment-based attacks
  clean = clean.replace(/<!--[\s\S]*?-->/g, '');

  return clean;
}

/**
 * Sanitize text for SAFE DOM insertion as text content (not HTML).
 * Use this when you want to render user content as PLAIN TEXT, not HTML.
 * Escapes <, >, &, ", ' so they render literally, not as markup.
 *
 * @param {string} text — raw untrusted text
 * @returns {string} — HTML-escaped text safe for innerHTML
 */
export function escapeHtml(text) {
  if (!text || typeof text !== 'string') return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Combined: escape HTML entities AND strip any remaining tags.
 * Use for the HIGHEST security contexts — e.g., rendering LLM output
 * that should NEVER contain any HTML markup.
 *
 * @param {string} text — raw untrusted text
 * @returns {string} — plain text with all HTML entities escaped
 */
export function sanitizeToText(text) {
  if (!text || typeof text !== 'string') return '';
  // First pass: sanitizeHtml catches malicious constructs
  const sanitized = sanitizeHtml(text);
  // Second pass: escape any remaining angle brackets as text
  return escapeHtml(sanitized);
}
