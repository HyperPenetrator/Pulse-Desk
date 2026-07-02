# PulseDesk Code Review Graph

This document serves as a visual guide and code review graph for **PulseDesk** (formerly known as Swasthya Grid). It outlines the architecture, component interactions, database schema, and data flows to facilitate codebase reviews.

## System Architecture Overview

PulseDesk is an integrated, offline-first healthcare management and emergency dispatch system. The system comprises a PWA frontend built with Next.js and a FastAPI backend with background task capabilities and third-party integrations.

```mermaid
graph TD
    subgraph Frontend [Next.js PWA Client]
        PP[Public Portal /]
        DS[Dashboard Switcher]
        R_DB[Receptionist Dashboard]
        PHC_DB[PHC In-charge Dashboard]
        DA_DB[District Admin Dashboard]
        DexieDB[(Dexie Offline DB)]
        SW[Serwist Service Worker]
    end

    subgraph Backend [FastAPI Server]
        API[API Endpoints /main.py]
        Voice[Voice Router /voice.py]
        WebHook[Webhook Router /webhook.py]
        ETL[ETL Services /etl.py]
        Cron[Cron Jobs /cron_jobs.py]
        Ref[Reference Services /reference_service.py]
        SQL[SQLAlchemy ORM /models.py]
    end

    subgraph Storage [Databases & Cache]
        SQLite[(SQLite healthify.db)]
        Redis[(Redis Cache)]
    end

    subgraph Integrations [External Services]
        Twilio[Twilio Voice / SMS]
        G_Maps[Google Maps API]
        Firestore[(Google Firestore Real-time Sync)]
    end

    %% Frontend Interactions
    PP -->|Intake Submission| API
    DS --> R_DB
    DS --> PHC_DB
    DS --> DA_DB
    R_DB <-->|Offline Walk-ins & Logs| DexieDB
    DexieDB <--> SW
    SW -->|Background Sync| API

    %% Backend Interactions
    API <--> SQL
    Voice <--> SQL
    WebHook <--> SQL
    ETL <--> SQL
    Cron <--> SQL
    Ref <--> SQL

    SQL <--> SQLite
    API <--> Redis

    %% Integrations
    Voice <--> Twilio
    WebHook <--> Twilio
    API --> G_Maps
    API --> Firestore
    Cron --> Firestore
```

---

## Component Details & File Mapping

### 1. Frontend Client (`/frontend`)
*   **Public Intake Portal** ([frontend/src/app/page.tsx](file:///D:/WebDevProject/PulseDesk/frontend/src/app/page.tsx)):
    *   *Features:* Symptom submission, GPS or preset manual geolocation.
    *   *Backend Call:* POST `/api/v1/intake`.
*   **Dashboard Switcher** ([frontend/src/app/DashboardSwitcher.tsx](file:///D:/WebDevProject/PulseDesk/frontend/src/app/DashboardSwitcher.tsx)):
    *   *Features:* Allows switching roles between Receptionist, PHC In-charge, and District Admin.
*   **Receptionist Dashboard** ([frontend/src/app/receptionist/page.tsx](file:///D:/WebDevProject/PulseDesk/frontend/src/app/receptionist/page.tsx)):
    *   *Features:* Patient registration, local walk-in log management, offline capability using Dexie.js.
*   **PHC In-charge Dashboard** ([frontend/src/app/phc-incharge/page.tsx](file:///D:/WebDevProject/PulseDesk/frontend/src/app/phc-incharge/page.tsx)):
    *   *Features:* Inventory tracking, daily footfall monitoring, bed management, staff attendance marking.
*   **District Admin Dashboard** ([frontend/src/app/district-admin/page.tsx](file:///D:/WebDevProject/PulseDesk/frontend/src/app/district-admin/page.tsx)):
    *   *Features:* District-wide KPI maps, resource redistribution tools, alert monitors.
*   **Service Worker & Offline Storage** ([frontend/src/lib/db.ts](file:///D:/WebDevProject/PulseDesk/frontend/src/lib/db.ts) & [frontend/src/app/sw.ts](file:///D:/WebDevProject/PulseDesk/frontend/src/app/sw.ts)):
    *   Uses Dexie to queue local transactions (walk-ins, footfalls) and Serwist for service worker caching.

### 2. Backend Server (`/backend`)
*   **App Core** ([backend/main.py](file:///D:/WebDevProject/PulseDesk/backend/main.py)):
    *   Configures FastAPI, registers CORS, imports routes, and exposes main API endpoints:
        *   `POST /api/v1/intake` - Classifies severities and queries distances to assign dispatches.
        *   `GET /api/v1/facilities` - Fetches all seeded facilities.
*   **Models & ORM** ([backend/models.py](file:///D:/WebDevProject/PulseDesk/backend/models.py)):
    *   Maps SQLAlchemy classes to database tables:
        *   `Facility`, `Staff`, `AttendanceLog`, `InventoryItem`, `FootfallLog`, `PatientSession`, `Dispatch`, `Alert`.
        *   Reference tables: `CensusReference`, `NFHSReference`, `DataGovInReference`.
*   **Voice Interface** ([backend/voice.py](file:///D:/WebDevProject/PulseDesk/backend/voice.py)):
    *   Handles interactive voice response (IVR) triage calls via Twilio.
*   **Webhook Interface** ([backend/webhook.py](file:///D:/WebDevProject/PulseDesk/backend/webhook.py)):
    *   Handles webhooks for Twilio messaging and callback confirmations.
*   **ETL Pipeline** ([backend/etl.py](file:///D:/WebDevProject/PulseDesk/backend/etl.py)):
    *   Consolidates demographic, geographic, and facility statistics.
*   **Cron Jobs** ([backend/cron_jobs.py](file:///D:/WebDevProject/PulseDesk/backend/cron_jobs.py)):
    *   Performs regular checkups (e.g. bed surges, stock-out detection, redistribution alerts).

---

## Database Relationships

The following entity-relationship diagram shows the relational schema in SQLite (`healthify.db`):

```mermaid
erDiagram
    FACILITY ||--o{ STAFF : employs
    FACILITY ||--o{ INVENTORY_ITEM : stocks
    FACILITY ||--o{ FOOTFALL_LOG : tracks
    FACILITY ||--o{ DISPATCH : receives
    FACILITY ||--o{ ALERT : triggers
    
    STAFF ||--o{ ATTENDANCE_LOG : records

    PATIENT_SESSION ||--|| DISPATCH : initiates

    FACILITY {
        uuid id PK
        string name
        string type
        string district_code
        float lat
        float lng
        int sanctioned_beds
        int available_beds
        int sanctioned_staff
    }

    STAFF {
        uuid id PK
        uuid facility_id FK
        string role
        string name
    }

    INVENTORY_ITEM {
        uuid id PK
        uuid facility_id FK
        string medicine_name
        int current_stock
        float avg_daily_burn_rate
        int supply_lead_time
        float drp_value
    }

    PATIENT_SESSION {
        uuid id PK
        string channel
        string raw_text
        string language_code
        float confidence_score
        string severity
        datetime created_at
    }

    DISPATCH {
        uuid id PK
        uuid patient_session_id FK
        uuid facility_id FK
        string status
        float lat
        float lng
        datetime eta
    }

    ALERT {
        uuid id PK
        string type
        uuid facility_id FK
        string district_code
        string status
        string description
        datetime created_at
    }
```
