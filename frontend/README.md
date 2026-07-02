# PulseDesk Frontend

This is the Next.js frontend application for **PulseDesk** (formerly Swasthya Grid). It features a responsive, PWA-enabled design with specialized dashboards for healthcare workers.

## Tech Stack
- **Framework:** Next.js 16 (App Router)
- **Styling:** Tailwind CSS v4 & @tailwindcss/postcss
- **Component Library:** Tremor & Lucide React
- **PWA Tooling:** Serwist (`@serwist/next`)
- **Offline DB:** Dexie.js (IndexDB wrapper)
- **Animations:** Framer Motion

## Core Features & Routes
- **Public Portal** (`/`): Intake form for patients to report symptoms and trigger automated triage and dispatch.
- **Dashboard Switcher** (`/`): Header-based toggle to navigate between different role dashboards.
- **Receptionist Dashboard** (`/receptionist`): View patient queues and log offline walk-ins.
- **PHC In-charge Dashboard** (`/phc-incharge`): Monitor beds, staff attendance logs, and inventory levels.
- **District Admin Dashboard** (`/district-admin`): High-level stats, disease maps, and resource redistribution alerts.

## Offline Capabilities
- Uses **Dexie.js** to manage local client databases:
  *   Stores offline walk-in registrations.
  *   Caches footfall logs.
- Uses **Serwist** service workers for resource caching and background sync capabilities when network states change.

## Getting Started

1. Install dependencies:
   ```bash
   npm install
   ```
2. Configure `.env.local`:
   ```env
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
4. Build for production:
   ```bash
   npm run build
   ```
