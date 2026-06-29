import os
import sys
from sqlalchemy.orm import Session

# Set path to import models and config
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from config import settings
from models import CensusReference, NFHSReference, DataGovInReference

def get_census_data(district_code: str, db: Session) -> dict:
    if settings.REFERENCE_DATA_SOURCE == "bigquery":
        try:
            from google.cloud import bigquery
            client = bigquery.Client(project=settings.FIREBASE_PROJECT_ID or "swasthya-grid")
            query = f"""
                SELECT district_code, catchment_population, age_cohort_under_5, age_cohort_over_60
                FROM `{settings.FIREBASE_PROJECT_ID or "swasthya-grid"}.reference_data.census_reference`
                WHERE district_code = @district_code
                LIMIT 1
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("district_code", "STRING", district_code)
                ]
            )
            query_job = client.query(query, job_config=job_config)
            results = list(query_job.result())
            if results:
                row = results[0]
                return {
                    "district_code": row.district_code,
                    "catchment_population": row.catchment_population,
                    "age_cohort_under_5": row.age_cohort_under_5,
                    "age_cohort_over_60": row.age_cohort_over_60,
                }
        except Exception as e:
            print(f"Error querying BigQuery for Census data: {e}. Falling back to SQLite.")
            
    # Fallback to local SQLite database
    ref = db.query(CensusReference).filter(CensusReference.district_code == district_code).first()
    if ref:
        return {
            "district_code": ref.district_code,
            "catchment_population": ref.catchment_population,
            "age_cohort_under_5": ref.age_cohort_under_5,
            "age_cohort_over_60": ref.age_cohort_over_60,
        }
    return None

def get_nfhs_data(district_code: str, db: Session) -> dict:
    if settings.REFERENCE_DATA_SOURCE == "bigquery":
        try:
            from google.cloud import bigquery
            client = bigquery.Client(project=settings.FIREBASE_PROJECT_ID or "swasthya-grid")
            query = f"""
                SELECT district_code, seasonal_vector_weight, disease_burden_indicators
                FROM `{settings.FIREBASE_PROJECT_ID or "swasthya-grid"}.reference_data.nfhs_reference`
                WHERE district_code = @district_code
                LIMIT 1
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("district_code", "STRING", district_code)
                ]
            )
            query_job = client.query(query, job_config=job_config)
            results = list(query_job.result())
            if results:
                row = results[0]
                return {
                    "district_code": row.district_code,
                    "seasonal_vector_weight": row.seasonal_vector_weight,
                    "disease_burden_indicators": row.disease_burden_indicators,
                }
        except Exception as e:
            print(f"Error querying BigQuery for NFHS data: {e}. Falling back to SQLite.")
            
    # Fallback to local SQLite database
    ref = db.query(NFHSReference).filter(NFHSReference.district_code == district_code).first()
    if ref:
        return {
            "district_code": ref.district_code,
            "seasonal_vector_weight": ref.seasonal_vector_weight,
            "disease_burden_indicators": ref.disease_burden_indicators,
        }
    return None

def get_datagovin_data(district_code: str, db: Session) -> dict:
    if settings.REFERENCE_DATA_SOURCE == "bigquery":
        try:
            from google.cloud import bigquery
            client = bigquery.Client(project=settings.FIREBASE_PROJECT_ID or "swasthya-grid")
            query = f"""
                SELECT district_code, sanctioned_staff_count, supply_lead_time_baseline
                FROM `{settings.FIREBASE_PROJECT_ID or "swasthya-grid"}.reference_data.datagovin_reference`
                WHERE district_code = @district_code
                LIMIT 1
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("district_code", "STRING", district_code)
                ]
            )
            query_job = client.query(query, job_config=job_config)
            results = list(query_job.result())
            if results:
                row = results[0]
                return {
                    "district_code": row.district_code,
                    "sanctioned_staff_count": row.sanctioned_staff_count,
                    "supply_lead_time_baseline": row.supply_lead_time_baseline,
                }
        except Exception as e:
            print(f"Error querying BigQuery for data.gov.in data: {e}. Falling back to SQLite.")
            
    # Fallback to local SQLite database
    ref = db.query(DataGovInReference).filter(DataGovInReference.district_code == district_code).first()
    if ref:
        return {
            "district_code": ref.district_code,
            "sanctioned_staff_count": ref.sanctioned_staff_count,
            "supply_lead_time_baseline": ref.supply_lead_time_baseline,
        }
    return None
