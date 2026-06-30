/**
 * Ambient declarations for build-time globals + non-TS module imports used by the
 * PORTED superbrain tree, so `tsc --noEmit` is clean WITHOUT editing src/superbrain/**.
 *
 * These live in the PRODUCT tree (src/types/) and survive `npm run port`.
 *
 *  - `process.env.*`: the superbrain adapter reads Next-style `process.env`
 *    (NEXT_PUBLIC_AIOS_URL / NODE_ENV). The Vite build statically replaces these
 *    via vite.config `define`; this only types them for tsc. Deliberately minimal
 *    — NOT the full @types/node global surface.
 *  - `*.module.css` / `*.css`: CSS-module + side-effect CSS imports have no TS
 *    type; declare them so the imports resolve.
 */

declare const process: {
  env: {
    NODE_ENV?: 'development' | 'production' | 'test' | string;
    NEXT_PUBLIC_AIOS_URL?: string;
    [key: string]: string | undefined;
  };
};

declare module '*.module.css' {
  const classes: { readonly [key: string]: string };
  export default classes;
}

declare module '*.css';
