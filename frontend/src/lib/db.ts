import Dexie, { type EntityTable } from 'dexie';

interface OfflineWalkIn {
  id?: number;
  patient_name: string;
  age: number;
  gender: string;
  symptoms: string;
  facility_id: string;
  synced: 0 | 1; // 0 for false, 1 for true
}

interface OfflineFootfall {
  id?: number;
  facility_id: string;
  date: string;
  count: number;
  synced: 0 | 1;
}

const db = new Dexie('HealthifyOfflineDB') as Dexie & {
  walkIns: EntityTable<OfflineWalkIn, 'id'>;
  footfallLogs: EntityTable<OfflineFootfall, 'id'>;
};

db.version(1).stores({
  walkIns: '++id, facility_id, synced',
  footfallLogs: '++id, facility_id, date, synced',
});

export { db };
