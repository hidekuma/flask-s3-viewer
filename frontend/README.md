# flask-s3-viewer frontend

Tailwind CSS build pipeline for the bundled templates.

The compiled CSS lives at `../flask_s3_viewer/blueprints/static/css/app.css`
and is shipped inside the Python wheel. Maintainers must rebuild after any
template change so the JIT-extracted utility classes stay in sync.

## Setup

```bash
cd frontend
npm install
```

## Build

```bash
npm run build   # one-shot minified build → ../flask_s3_viewer/blueprints/static/css/app.css
npm run watch   # rebuild on template change (dev)
```

## What lives here

- `package.json` — devDependencies (`tailwindcss`, `@tailwindcss/forms`)
- `tailwind.config.js` — scans `flask_s3_viewer/blueprints/templates/**/*.html`
- `src/app.css` — `@tailwind base/components/utilities` entry

The build output is committed to git so end users do not need Node installed.
