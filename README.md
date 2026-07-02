# PulseDesk (Swasthya Grid)

PulseDesk is an integrated, offline-first healthcare management and emergency dispatch system. It is designed to handle patient triage, real-time facility tracking, and dynamic dispatch coordination.

For a detailed visual guide of the codebase architecture and relationships, see the [Code Review Graph](file:///D:/WebDevProject/PulseDesk/code-review-graph.md).

## Key Features

1.  **Patient Intake & Triage Portal**: Public portal to describe symptoms and determine severity using keyword mapping (e.g., chest pain, breathing difficulty trigger emergency).
2.  **Ambulance Dispatch & Bed Allocation**: Automatically coordinates the closest facility using a simulated or actual Google Maps Distance Matrix API and Firestore mirroring.
3.  **Role-Based Dashboards**:
    *   **Receptionist**: View patient logs and register walk-ins.
    *   **PHC In-charge**: Monitor daily footfall, track medicine inventory, and update available beds.
    *   **District Admin**: Access district-wide health KPIs, view alerts, and trigger resources redistribution.
4.  **Offline-First & PWA**: Supports offline queuing of walk-ins and footfall logs using **Dexie.js** and **Serwist** service workers for background synchronization once network connectivity returns.
5.  **Multi-Channel Integrations**: Integrates voice triage via Twilio and mirrors alerts/dispatches to Firebase Firestore.

## Project Structure

This is a monorepo consisting of:
- `backend/`: A FastAPI backend handling the core logic, database interactions, and integrations (Twilio Voice, Google Maps, Firebase, etc.).
- `frontend/`: A Next.js 16 frontend application styled with Tailwind CSS v4 and Tremor, featuring PWA service worker setups.

## Getting Started

### Prerequisites
- Node.js (v18+)
- Python 3.10+
- SQLite (local development)
- Redis

### Backend Setup
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create a virtual environment:
   ```bash
   python -m venv venv
   ```
3. Activate the virtual environment:
   *   Windows: `venv\Scripts\activate`
   *   Linux/Mac: `source venv/bin/activate`
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Start the backend:
   ```bash
   uvicorn main:app --reload
   ```
   The API will be available at http://localhost:8000
6. Seed mock data:
   ```bash
   python seed.py
   ```

### Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
   The UI will be available at http://localhost:3000

## Environment Variables
Ensure you set up your `.env` files in both the `frontend/` and `backend/` directories. Refer to `.env.local` or `.env.example` configurations.
- Backend: Requires configuration for Firebase and Twilio if using live sync or call functionalities.
- Frontend: `NEXT_PUBLIC_API_URL` pointing to your running FastAPI backend.
