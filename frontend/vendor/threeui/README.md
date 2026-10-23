# Kage source integration

This private local package exposes `KageLandingPage` from the [registered ThreeUI source bundle](https://threeui.com/source-code/kage-landing-page.json), revision `c8e06b90397a`. It is a source adapter, not the complete published ThreeUI library.

The five registered React/TypeScript/CSS files are preserved byte-for-byte under `src/`. `index.tsx` copies the exact Kage function from `LandingPages.tsx` and imports its original frame, typography hook, and recipe. The full `LandingPages.tsx` also imports unrelated scenes absent from the registered bundle; it is retained for verification and is not the package entry point.

The canonical HTML, embedded font stylesheet, Three.js runtime, and 14 WebP assets live under the application's `public/landing-pages/`, at the original paths. These were copied byte-for-byte from `@designcodeio/threeui@1.2.0` and all match the requested hashes. The public website rewrites asset URLs and externalizes embedded fonts, so its served files are not used in the application.

`source-manifest.json` records all 22 expected sizes and SHA-256 hashes. Run `npm run verify:kage` from `frontend/` to check them; the production build also runs this verification. `.gitattributes` prevents checkout line-ending conversion from changing the registered bytes.

The shared stylesheet also references Fragment Mono. Its original bytes were extracted from the published package's embedded CSS font into `src/shaders/fonts/fragment-mono.woff2` and recorded in `supportFiles`, so Vite can resolve the shared stylesheet without changing it.

The HTML is loaded locally by the original `LandingPageFrame`. Typography is applied through the original customization hook. The configured Onest faces, Japanese face, wordmark, Three.js, and images require no external requests. The host page provides a separate Open Studio button; the authored Kage document and navigation are unchanged.

Upstream license and asset/font notices are retained in this directory.

After building, run `backend/venv/Scripts/python.exe -m pytest tests/test_kage_browser.py -q` from the repository root. The checks serve the production build on a temporary local port, use headless Edge, and cover WebGL, typography, chapter navigation, cloth cards, the mobile menu, reduced motion, local-only requests, and studio persistence. Screenshots are saved to `test_artifacts/kage/`.
