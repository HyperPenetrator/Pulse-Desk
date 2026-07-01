# Swasthya Grid

Swasthya Grid is an integrated healthcare management and emergency dispatch system, designed to handle patient triage, real-time facility tracking, and dynamic dispatch coordination.

## Project Structure

This is a monorepo consisting of:
- `backend/`: A FastAPI backend handling the core logic, database interactions, and integrations (Twilio Voice, Google Maps, etc.).
- `frontend/`: A Next.js frontend application featuring dashboards for receptionists, PHC in-charges, and district administrators.

## Getting Started

### Prerequisites
- Node.js (v18+)
- Python 3.10+
- PostgreSQL or SQLite (for local development)
- Redis

### Backend Setup
1. Navigate to the backend directory: `cd backend`
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Start the backend: `uvicorn main:app --reload`
   - The API will be available at http://localhost:8000

### Frontend Setup
1. Navigate to the frontend directory: `cd frontend`
2. Install dependencies: `npm install`
3. Run the development server: `npm run dev`
   - The UI will be available at http://localhost:3000

## Environment Variables
Ensure you set up your `.env` files in both the `frontend/` and `backend/` directories. Refer to the `.env.example` if available or contact the administrator for required keys (e.g., Firebase, Maps API, Twilio).

## Deployment
This project is configured to deploy the backend to Railway (`railway.toml` provided) and the frontend to Vercel (auto-detected Next.js).
