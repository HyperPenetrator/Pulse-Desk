import os
import sys
import argparse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set path to import models and config
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from config import settings
from models import Base, CensusReference, NFHSReference, DataGovInReference

# Synthetic data matching the 2 seeded districts from Stage 1: 'KA-BNG', 'MH-MUM'
SYNTHETIC_CENSUS = [
    {
        "district_code": "KA-BNG",
        "catchment_population": 150000,
        "age_cohort_under_5": 0.12,  # 12% of population
        "age_cohort_over_60": 0.08   # 8% of population
    },
    {
        "district_code": "MH-MUM",
        "catchment_population": 300000,
        "age_cohort_under_5": 0.10,
        "age_cohort_over_60": 0.11
    }
]

SYNTHETIC_NFHS = [
    {
        "district_code": "KA-BNG",
        "seasonal_vector_weight": 12.5,
        "disease_burden_indicators": '{"malaria_prevalence": 0.02, "dengue_prevalence": 0.05}'
    },
    {
        "district_code": "MH-MUM",
        "seasonal_vector_weight": 25.0,
        "disease_burden_indicators": '{"malaria_prevalence": 0.04, "dengue_prevalence": 0.08}'
    }
]

SYNTHETIC_DATAGOVIN = [
    {
        "district_code": "KA-BNG",
        "sanctioned_staff_count": 25,
        "supply_lead_time_baseline": 7
    },
    {
        "district_code": "MH-MUM",
        "sanctioned_staff_count": 50,
        "supply_lead_time_baseline": 10
    }
]


class BaseLoader:
    def load_census(self, data: list[dict]):
        raise NotImplementedError

    def load_nfhs(self, data: list[dict]):
        raise NotImplementedError

    def load_datagovin(self, data: list[dict]):
        raise NotImplementedError


class SQLiteLoader(BaseLoader):
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
        # Ensure tables exist
        Base.metadata.create_all(bind=self.engine)

    def load_census(self, data: list[dict]):
        session = self.Session()
        try:
            for item in data:
                # Merge / upsert
                ref = session.query(CensusReference).filter_by(district_code=item["district_code"]).first()
                if not ref:
                    ref = CensusReference(district_code=item["district_code"])
                    session.add(ref)
                ref.catchment_population = item["catchment_population"]
                ref.age_cohort_under_5 = item["age_cohort_under_5"]
                ref.age_cohort_over_60 = item["age_cohort_over_60"]
            session.commit()
            print("Successfully loaded Census data to SQLite.")
        except Exception as e:
            session.rollback()
            print(f"Error loading Census data to SQLite: {e}")
            raise e
        finally:
            session.close()

    def load_nfhs(self, data: list[dict]):
        session = self.Session()
        try:
            for item in data:
                ref = session.query(NFHSReference).filter_by(district_code=item["district_code"]).first()
                if not ref:
                    ref = NFHSReference(district_code=item["district_code"])
                    session.add(ref)
                ref.seasonal_vector_weight = item["seasonal_vector_weight"]
                ref.disease_burden_indicators = item["disease_burden_indicators"]
            session.commit()
            print("Successfully loaded NFHS data to SQLite.")
        except Exception as e:
            session.rollback()
            print(f"Error loading NFHS data to SQLite: {e}")
            raise e
        finally:
            session.close()

    def load_datagovin(self, data: list[dict]):
        session = self.Session()
        try:
            for item in data:
                ref = session.query(DataGovInReference).filter_by(district_code=item["district_code"]).first()
                if not ref:
                    ref = DataGovInReference(district_code=item["district_code"])
                    session.add(ref)
                ref.sanctioned_staff_count = item["sanctioned_staff_count"]
                ref.supply_lead_time_baseline = item["supply_lead_time_baseline"]
            session.commit()
            print("Successfully loaded data.gov.in data to SQLite.")
        except Exception as e:
            session.rollback()
            print(f"Error loading data.gov.in data to SQLite: {e}")
            raise e
        finally:
            session.close()


class BigQueryLoader(BaseLoader):
    def __init__(self, project_id: str):
        self.project_id = project_id
        try:
            from google.cloud import bigquery
            self.client = bigquery.Client(project=project_id)
        except ImportError:
            print("google-cloud-bigquery package not installed. Running in mock/dry-run BigQuery mode.")
            self.client = None

    def _load_bq_table(self, table_id: str, data: list[dict]):
        if not self.client:
            print(f"[Mock BigQuery] Would load {len(data)} rows into table: {table_id}")
            return
        
        # Load logic using bigquery client
        from google.cloud import bigquery
        dataset_ref = self.client.dataset("reference_data")
        table_ref = dataset_ref.table(table_id)
        
        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_TRUNCATE",
            autodetect=True,
        )
        
        load_job = self.client.load_table_from_json(
            data, table_ref, job_config=job_config
        )
        load_job.result()  # Waits for the job to complete.
        print(f"Successfully loaded {len(data)} rows to BigQuery table {table_id}.")

    def load_census(self, data: list[dict]):
        self._load_bq_table("census_reference", data)

    def load_nfhs(self, data: list[dict]):
        self._load_bq_table("nfhs_reference", data)

    def load_datagovin(self, data: list[dict]):
        self._load_bq_table("datagovin_reference", data)


def run_etl(source_type: str = None):
    if not source_type:
        source_type = settings.REFERENCE_DATA_SOURCE

    print(f"Starting ETL. Target source type: {source_type}")
    if source_type == "bigquery":
        loader = BigQueryLoader(project_id=settings.FIREBASE_PROJECT_ID or "swasthya-grid")
    else:
        loader = SQLiteLoader(db_url=settings.DATABASE_URL)

    loader.load_census(SYNTHETIC_CENSUS)
    loader.load_nfhs(SYNTHETIC_NFHS)
    loader.load_datagovin(SYNTHETIC_DATAGOVIN)
    print("ETL job completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run reference data ETL job")
    parser.add_argument("--source", type=str, choices=["sqlite", "bigquery"], help="Force source destination type")
    args = parser.parse_args()
    run_etl(args.source)
