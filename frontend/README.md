# Frontend (Next.js)

PlagiaCheck frontend built with Next.js (App Router). Includes the marketing landing page and analysis flows with a shared, theme-aware UI.

## Requirements

- Node.js 18+
- npm (or pnpm/yarn/bun)

## Setup

```bash
npm install
```

## Run

```bash
npm run dev
```

App runs at http://localhost:3000.

## Build

```bash
npm run build
npm run start
```

## Scripts

- `npm run dev` - Dev server
- `npm run build` - Production build
- `npm run start` - Start production server
- `npm run lint` - ESLint

## App Structure

- `app/` - Next.js App Router pages
- `app/analyze/*` - Analysis pages (exact, fuzzy, semantic, AI-detect, web-scan, license, cross-batch)
- `app/components/` - Shared UI components and theme provider
- `app/globals.css` - Design tokens, themes, utilities, and animations

## Theming

Theme is controlled via `ThemeProvider` and CSS variables.

- Light and dark palettes are defined in `app/globals.css` using `:root` and `.dark` tokens.
- The `ThemeProvider` sets the `dark` class on `html` and persists the preference in `localStorage`.
- Theme toggle buttons are in `app/components/Navbar.tsx` and `app/analyze/AnalyzerLayout.tsx`.

## Notes

- Inline styles rely on CSS variables to stay theme-safe and consistent.
- PDF/XLSX uploads are supported in the analyze flows via `pdfjs-dist` and `xlsx`.