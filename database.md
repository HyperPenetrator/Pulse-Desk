# context.md - Smart Health AI-Driven Platform

## 1. Project Overview & Vision
This project delivers an intelligent backend and analytical engine for **Track 3: Smart Health (AI-Driven Health Center & Supply Chain Management)**. 

The platform bridges the gap between real-time operational data at local Primary Health Centres (PHCs) / Community Health Centres (CHCs) and static macro-level public health datasets. By feeding **data.gov.in**, **Census**, and **NFHS** data into our AI models, the platform transitions rural healthcare from reactive manual tracking to predictive, automated resource management.

---

## 2. Problem Statement Alignment

| Hackathon Challenge Metric | Operational Gap | Data-Driven Solution Context |
| :--- | :--- | :--- |
| **Stock Monitoring** | Recurring medicine stock-outs, unmonitored consumption rates. | Cross-reference local inventory with **data.gov.in** Essential Meds lists and **NFHS** regional disease burdens to flag shortages early. |
| **Patient Footfall** | Unmanaged spikes in patient volume, unexpected seasonal epidemics. | Forecast patient influx using **Census** catchment populations and seasonal health trends from **NFHS**. |
| **Bed & Test Availability** | Zero real-time visibility for district admins to coordinate transfers. | Benchmark current occupancy against **data.gov.in** infrastructure statistics to trigger smart redistribution. |
| **Doctor Attendance** | Unpredictable attendance, leading to under-resourced centers. | Track deviations from **data.gov.in (National Health Profile)** sanctioned staff counts to flag underperformance. |

---

## 3. Dataset Integrations & Analytical Anchors

### A. data.gov.in (Operational Baselines)
* **Role in System:** Establishes the standard operating benchmarks for every tier of the healthcare facility.
* **Key Components Handled:**
  * **National Health Profile (NHP):** Used to retrieve sanctioned vs. actual strength of doctors, specialists, and nursing staff per district.
  * **Logistics & Procurement Data:** Feeds standard drug formularies and expected supply lead times into the predictive stock-out warning engine.

### B. Census of India (Demographic Context)
* **Role in System:** Provides the population denominator to calculate realistic healthcare demand within a geographic block.
* **Key Components Handled:**
  * **Catchment Population:** Maps total block/village population to the nearest PHC/CHC.
  * **Vulnerability Demographics:** Extracts age-cohort splits (e.g., infants under 5, senior citizens) to dynamically weight the demand for pediatric or geriatric medical supplies.

### C. National Family Health Survey (NFHS-5 / NFHS-6)
* **Role in System:** Acts as the medical baseline for localized disease prevalence and historical health vulnerability.
* **Key Components Handled:**
  * **Disease Burden Mapping:** Integrates district-level trends on communicable outbreaks, chronic illnesses (hypertension, diabetes), and acute conditions.
  * **Utilization Tendencies:** Factors in regional rates of institutional delivery and immunization to predict recurring diagnostic and vaccine load.

---

## 4. AI Engine Logic & Data Flow

1. **Ingestion Layer:** Real-time variables (current stock levels, daily footfall, active beds, staff attendance) are pushed via the platform's multilingual interfaces.
2. **Contextual Enrichment:** The system queries the pre-processed database of **Census + NFHS + data.gov.in** variables corresponding to that specific health facility’s district code.
3. **Predictive Processing:**
   * **Stock Runway:** The system calculates inventory depletion rates not just on historic usage, but on the *predicted seasonal demand* flagged by NFHS trends for that month.
   * **Resource Redistribution:** If Facility A is experiencing a surge while Facility B (within a 15km radius) has low footfall relative to its Census demographic baseline, the AI generates a smart resource redistribution token for district logistics.
4. **Administrative Escalation:** When a facility's operational metrics drop significantly below the **data.gov.in** infrastructure requirements for an extended duration, an automated "Underperforming Facility" flag is pushed to the district admin dashboard.

---

## 5. Primary Evaluative Formulas

* **Facility Stress Index (FSI):** Evaluates whether current footfall matches infrastructure capacity.
  $$\text{FSI} = \frac{\text{Real-time Daily Footfall}}{\text{Census Catchment Population} \times \text{Available Beds Baseline}}$$

* **Dynamic Reorder Point (DRP):** Calculates when to trigger a stock-out warning before it happens.
  $$\text{DRP} = (\text{Average Daily Burn Rate} \times \text{Supply Lead Time}) + \text{NFHS Seasonal Vector Weight}$$