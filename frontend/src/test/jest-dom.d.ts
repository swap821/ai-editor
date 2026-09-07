// Registers @testing-library/jest-dom's matcher TYPES against vitest's
// `Assertion` interface.
//
// WHY THIS FILE EXISTS. `tsconfig.json` sets `types: ['vitest/globals']`, and an
// explicit `types` array is an allowlist: TypeScript then loads only those
// ambient packages. Under vitest 4 the jest-dom matchers still type-checked,
// because `vitest/globals` carried a chai-derived `Assertion` loose enough to
// accept them. vitest 5 tightened that type, and 196 errors appeared at once --
// `toBeInTheDocument`, `toHaveAttribute`, `toBeDisabled` and friends were
// suddenly "not a property of Assertion".
//
// The matchers were always registered at RUNTIME by `src/test/setup.js`; only
// their types were missing. `@testing-library/jest-dom/vitest` is the subpath
// whose declarations augment vitest specifically, and importing it from a file
// inside `include: ['src']` is what puts the augmentation into the program --
// a subpath cannot be named in `types`, which takes package roots only.
import '@testing-library/jest-dom/vitest';
