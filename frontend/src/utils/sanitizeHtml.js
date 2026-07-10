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

/**
 * Sanitize <a> tags: only allow http://, https://, mailto:, tel:, #anchor
 * hrefs, and rebuild the tag keeping ONLY href/rel/class/data-* — every
 * other attribute (including `style`, which the old attribute-preserving
 * approach let through unfiltered) is dropped rather than selectively
 * patched, so a new dangerous attribute can't reopen this hole later.
 */
function sanitizeAnchorTag(tagHtml) {
  if (!/^<a\b/i.test(tagHtml)) return tagHtml; // closing </a> — no attributes to filter

  const hrefMatch = tagHtml.match(/\s+href\s*=\s*["']([^"]*)["']/i);
  let safeHref = null;
  if (hrefMatch) {
    const href = hrefMatch[1].trim();
    const isSafe =
      href.startsWith('http://') ||
      href.startsWith('https://') ||
      href.startsWith('mailto:') ||
      href.startsWith('tel:') ||
      href.startsWith('#') ||
      href.startsWith('/') ||
      /^[a-zA-Z0-9_-]+\.html?$/i.test(href);
    if (isSafe) safeHref = href;
  }

  // Strip every attribute except class/data-* — href/rel are rebuilt below
  // from the validated value, never carried through unfiltered.
  let result = tagHtml.replace(/\s+[a-zA-Z_:][-\w:.]*\s*=\s*["'][^"']*["']/g, (attr) => {
    const attrName = attr.split('=')[0].trim().toLowerCase();
    if (attrName === 'class' || attrName.startsWith('data-')) return attr;
    return '';
  });

  if (safeHref) {
    const rel =
      safeHref.startsWith('http://') || safeHref.startsWith('https://')
        ? ' rel="noopener noreferrer"'
        : '';
    result = result.replace(/^<a\b/i, `<a href="${safeHref}"${rel}`);
  }

  return result;
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

  // 1. Remove ALL <script> tags and their content entirely (fixed-point loop
  //    to handle nested/obfuscated fragments that a single pass would miss).
  {
    const scriptBlock = /<script\b[^<]*(?:(?!<\/script[^>]*>)<[^<]*)*<\/script[^>]*>/gi;
    let prev;
    do { prev = clean; clean = clean.replace(scriptBlock, ''); } while (clean !== prev);
  }

  // 2. Remove other dangerous tags entirely
  clean = clean.replace(getDangerousTagPattern(), '');

  // 3. Strip ALL event handler attributes (fixed-point loop).
  {
    let prev;
    do { prev = clean; clean = clean.replace(EVENT_HANDLER_PATTERN, ''); } while (clean !== prev);
  }

  // 4. Strip dangerous URL schemes in attributes
  clean = clean.replace(DANGEROUS_URL_PATTERN, '');

  // 5. Strip CSS expression() (IE legacy)
  clean = clean.replace(EXPRESSION_PATTERN, '');

  // 6. Strip dangerous inline styles
  clean = clean.replace(DANGEROUS_STYLE_PATTERN, '');

  // 7. Filter to allowed tag whitelist + sanitize attributes
  clean = filterAllowedTags(clean);

  // 8. Defense-in-depth: catch any remaining <script...> patterns (fixed-point loop).
  {
    const scriptTag = /<\/?script\b[^>]*>/gi;
    while (scriptTag.test(clean)) {
      scriptTag.lastIndex = 0;
      clean = clean.replace(scriptTag, '');
    }
  }

  // 9. Catch HTML comment-based attacks (fixed-point loop).
  {
    const commentPat = /<!--[\s\S]*?-->/g;
    let prev;
    do { prev = clean; clean = clean.replace(commentPat, ''); } while (clean !== prev);
  }

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
