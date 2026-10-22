// Evaluated only with the optional visual subtree, BEFORE its first Text.
// Preserve main-thread typesetting and the existing strict CSP.
import '../superbrain/lib/troikaConfig';
import { configureTextBuilder } from 'troika-three-text';

if (import.meta.env.DEV && new URLSearchParams(window.location.search).get('physical-gallery') === 'journey') {
  configureTextBuilder({ useWorker: false, defaultFontURL: '/fonts/fixture-outfit.ttf' });
}
