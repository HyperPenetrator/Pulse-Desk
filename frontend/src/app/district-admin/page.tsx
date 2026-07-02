'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Card, ProgressBar, Badge } from '@tremor/react';
import { motion } from 'framer-motion';// ── Types ────────────────────────────────────────────────────────────────────
type FSIFacility = { facility_id: string; facility_name: string; fsi_value: number };
type FSIData = { district_code: string; average_fsi: number; facilities: FSIFacility[] };
type Trigger = { metric: string; value: number; threshold: number; detail: string };
type UnderperformingFacility = { facility_id: string; facility_name: string; facility_type: string; fsi_value: number; triggers: Trigger[] };
type RedistRequest = { alert_id: string; facility_id: string; facility_name: string; status: string; description: string; created_at: string };
type AttendanceFacility = { facility_id: string; facility_name: string; facility_type: string; sanctioned_staff: number; present_today: number; deviation: number; attendance_pct: number };
type DispatchItem = { dispatch_id: string; facility_name: string; facility_id: string; status: string; eta: string | null; symptom: string };
type FleetData = { pending: DispatchItem[]; enroute: DispatchItem[]; arrived: DispatchItem[]; total: number; district_code: string };
type BenchmarkData = {
  district_code: string; total_facilities: number;
  live_metrics: { avg_fsi: number; total_sanctioned_staff: number; total_staff_present_today: number; attendance_pct: number };
  census_reference: { catchment_population?: number; age_cohort_under_5?: number; age_cohort_over_60?: number };
  nfhs_reference: { seasonal_vector_weight?: number; disease_burden_indicators?: string };
  datagovin_reference: { sanctioned_staff_count?: number; supply_lead_time_baseline?: number };
  comparison: { staff_vs_benchmark: { actual: number; benchmark: number; gap: number }; seasonal_risk_weight: number; catchment_population: number };
};

const KNOWN_DISTRICTS = ['KA-BNG', 'MH-MUM'];

type Screen = 'fsi' | 'underperforming' | 'redistribution' | 'attendance' | 'fleet' | 'benchmarks';

const SCREENS: { id: Screen; label: string; icon: string }[] = [
  { id: 'fsi', label: 'FSI Heatmap', icon: '🌡️' },
  { id: 'underperforming', label: 'Flags', icon: '⚠️' },
  { id: 'redistribution', label: 'Redistribution', icon: '🔄' },
  { id: 'attendance', label: 'Attendance', icon: '📋' },
  { id: 'fleet', label: 'Fleet Status', icon: '🚑' },
  { id: 'benchmarks', label: 'Benchmarks', icon: '📊' },
];

// ── FSI colour helper ─────────────────────────────────────────────────────────
function fsiColor(val: number) {
  if (val > 0.001) return { bar: '#ef4444', badge: 'bg-rose-50 dark:bg-rose-500/20 text-rose-800 dark:text-rose-300 border border-rose-200 dark:border-rose-800/40', label: 'Critical' };
  if (val > 0.0005) return { bar: '#f59e0b', badge: 'bg-amber-50 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800/40', label: 'Elevated' };
  return { bar: '#10b981', badge: 'bg-emerald-50 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/40', label: 'Normal' };
}

export default function DistrictAdminDashboard() {
  const [token, setToken] = useState<string | null>(null);
  const [districtCode, setDistrictCode] = useState<string | null>(null);
  const [selectedDistrict, setSelectedDistrict] = useState<string>(KNOWN_DISTRICTS[0]);
  const [activeScreen, setActiveScreen] = useState<Screen>('fsi');

  // Data states
  const [fsiData, setFsiData] = useState<FSIData | null>(null);
  const [underperforming, setUnderperforming] = useState<UnderperformingFacility[]>([]);
  const [redistRequests, setRedistRequests] = useState<RedistRequest[]>([]);
  const [attendance, setAttendance] = useState<AttendanceFacility[]>([]);
  const [fleet, setFleet] = useState<FleetData | null>(null);
  const [benchmarks, setBenchmarks] = useState<BenchmarkData | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [drillFacility, setDrillFacility] = useState<UnderperformingFacility | null>(null);
  const [aiState, setAiState] = useState<'active' | 'applying' | 'applied' | 'dismissed'>('active');

  const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // ── Auth helpers ────────────────────────────────────────────────────────────
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const resp = await fetch(`${backendUrl}/api/v1/auth/mock-login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: 'district_admin', district_code: selectedDistrict }),
      });
      if (!resp.ok) throw new Error('Login failed');
      const data = await resp.json();
      localStorage.setItem('da_token', data.access_token);
      localStorage.setItem('da_district', selectedDistrict);
      setToken(data.access_token);
      setDistrictCode(selectedDistrict);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('da_token');
    localStorage.removeItem('da_district');
    setToken(null);
    setDistrictCode(null);
    setFsiData(null);
    setUnderperforming([]);
    setRedistRequests([]);
    setAttendance([]);
    setFleet(null);
    setBenchmarks(null);
  };

  // Re-hydrate from localStorage on mount
  useEffect(() => {
    const t = localStorage.getItem('da_token');
    const dc = localStorage.getItem('da_district');
    if (t && dc) { setToken(t); setDistrictCode(dc); }
  }, []);

  // ── Data fetching ───────────────────────────────────────────────────────────
  const fetchAll = useCallback(async () => {
    if (!token || !districtCode) return;
    const h = { Authorization: `Bearer ${token}` };
    const dc = districtCode;
    try {
      const [fsiR, upR, rrR, attR, flR, bmR] = await Promise.all([
        fetch(`${backendUrl}/api/v1/fsi/district/${dc}`, { headers: h }),
        fetch(`${backendUrl}/api/v1/district-admin/underperforming?district_code=${dc}`, { headers: h }),
        fetch(`${backendUrl}/api/v1/district-admin/redistribution-requests`, { headers: h }),
        fetch(`${backendUrl}/api/v1/district-admin/attendance-deviation?district_code=${dc}`, { headers: h }),
        fetch(`${backendUrl}/api/v1/district-admin/fleet?district_code=${dc}`, { headers: h }),
        fetch(`${backendUrl}/api/v1/district-admin/benchmarks?district_code=${dc}`, { headers: h }),
      ]);

      if (fsiR.status === 401 || fsiR.status === 403) { handleLogout(); return; }

      if (fsiR.ok) setFsiData(await fsiR.json());
      if (upR.ok) { const d = await upR.json(); setUnderperforming(d.underperforming || []); }
      if (rrR.ok) setRedistRequests(await rrR.json());
      if (attR.ok) { const d = await attR.json(); setAttendance(d.facilities || []); }
      if (flR.ok) setFleet(await flR.json());
      if (bmR.ok) setBenchmarks(await bmR.json());
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [token, districtCode, backendUrl]);

  useEffect(() => {
    if (!token || !districtCode) return;
    setIsLoading(true);
    fetchAll();
    const iv = setInterval(fetchAll, 5000);
    return () => clearInterval(iv);
  }, [token, districtCode, fetchAll]);

  // ── Redistribution approve / reject ────────────────────────────────────────
  const handleRedistAction = async (alertId: string, action: 'approved' | 'rejected') => {
    if (!token) return;
    setActionMsg(null);
    try {
      const resp = await fetch(`${backendUrl}/api/v1/redistribution/${alertId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ action }),
      });
      if (!resp.ok) throw new Error(`Action failed: ${resp.status}`);
      const data = await resp.json();
      setActionMsg(`Request ${data.new_status} successfully.`);
      // Optimistically update UI
      setRedistRequests(prev => prev.map(r => r.alert_id === alertId ? { ...r, status: action } : r));
    } catch (err: any) {
      setActionMsg(`Error: ${err.message}`);
    }
  };

  // ── AI Recommendations ──────────────────────────────────────────────────────
  const handleApplyAI = () => {
    setAiState('applying');
    setTimeout(() => {
      setAiState('applied');
    }, 2000);
  };

  const handleDismissAI = () => {
    setAiState('dismissed');
  };

  // ── Login screen ────────────────────────────────────────────────────────────
  if (!token) {
    return (
      <div className="min-h-screen bg-surface-alt dark:bg-slate-950 text-text-primary dark:text-slate-100 flex flex-col items-center justify-center p-6 selection:bg-violet-500 selection:text-black">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_#1e1b4b_0%,_transparent_60%)] pointer-events-none" />

        <div className="w-full max-w-md bg-surface-alt dark:bg-slate-900 border border-glass-border dark:border-slate-800 rounded-3xl p-8 shadow-2xl relative z-10">
          <div className="flex flex-col items-center mb-8">
            <div className="h-14 w-14 rounded-2xl bg-gradient-to-tr from-violet-600 to-indigo-400 flex items-center justify-center shadow-lg shadow-violet-500/25 mb-4">
              <svg className="w-7 h-7 text-text-primary dark:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-violet-400 to-indigo-300 bg-clip-text text-transparent">
              PulseDesk
            </h1>
            <p className="text-xs text-text-muted dark:text-slate-400 mt-1 uppercase tracking-widest">District Administrator</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-6">
            <div className="space-y-2">
              <label htmlFor="district-select" className="block text-xs font-semibold uppercase tracking-wider text-text-muted dark:text-slate-400">
                Select Your District
              </label>
              <select
                id="district-select"
                className="w-full bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-2xl px-4 py-3 text-text-primary dark:text-slate-100 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition"
                value={selectedDistrict}
                onChange={(e) => setSelectedDistrict(e.target.value)}
              >
                {KNOWN_DISTRICTS.map(dc => (
                  <option key={dc} value={dc}>{dc}</option>
                ))}
              </select>
            </div>

            {error && (
              <div className="bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/40 rounded-xl px-4 py-3 text-xs text-rose-800 dark:text-rose-300">{error}</div>
            )}

            <button
              id="login-button"
              type="submit"
              className="w-full py-4 rounded-2xl font-bold text-sm tracking-wide uppercase transition duration-200 bg-gradient-to-r from-violet-600 to-indigo-500 hover:from-violet-500 hover:to-indigo-400 text-text-primary dark:text-white shadow-lg shadow-violet-500/20"
            >
              Sign In as District Admin
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ── Dashboard ───────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-surface text-text-primary flex flex-col font-sans selection:bg-brand-primary/20">

      {/* Header */}
      <header className="relative w-full border-b border-glass-border bg-glass-bg backdrop-blur-md px-6 py-4 flex justify-between items-center z-20 shadow-glass-light">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-violet-600 to-indigo-400 flex items-center justify-center shadow-lg shadow-violet-500/20">
            <svg className="w-4 h-4 text-text-primary dark:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight bg-gradient-to-r from-violet-400 to-indigo-300 bg-clip-text text-transparent">
              PulseDesk
            </h1>
            <p className="text-[9px] text-text-muted dark:text-slate-400 uppercase tracking-widest -mt-0.5">District Admin Console</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div id="district-badge" className="text-xs bg-surface-alt dark:bg-slate-900 border border-glass-border dark:border-violet-900/50 rounded-full px-3 py-1.5 text-violet-700 dark:text-violet-300 flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-violet-500 animate-pulse" />
            District: {districtCode}
          </div>
          <button
            id="logout-button"
            onClick={handleLogout}
            className="text-xs bg-rose-50 dark:bg-rose-950/20 hover:bg-rose-100 dark:hover:bg-rose-950/40 border border-rose-200 dark:border-rose-900/40 text-rose-800 dark:text-rose-300 rounded-xl px-3.5 py-1.5 transition"
          >
            Sign Out
          </button>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="bg-brand-danger/20 border-b border-brand-danger/50 px-6 py-2 text-xs text-brand-danger text-center">⚠️ {error}</div>
      )}

      {/* Nav Tabs */}
      <nav className="sticky top-0 z-10 w-full border-b border-glass-border bg-glass-bg backdrop-blur-sm px-6 py-0 flex gap-1 overflow-x-auto shadow-glass-light">
        {SCREENS.map(s => (
          <button
            key={s.id}
            id={`tab-${s.id}`}
            onClick={() => setActiveScreen(s.id)}
            className={`flex items-center gap-1.5 px-4 py-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap border-b-2 transition-all duration-150 ${activeScreen === s.id
                ? 'border-violet-500 text-violet-700 dark:text-violet-300'
                : 'border-transparent text-slate-500 hover:text-text-muted dark:text-slate-300'
              }`}
          >
            <span>{s.icon}</span>{s.label}
            {s.id === 'redistribution' && redistRequests.filter(r => r.status === 'active').length > 0 && (
              <span className="ml-1 bg-violet-600 text-white text-[10px] rounded-full px-1.5 py-0.5 font-bold">
                {redistRequests.filter(r => r.status === 'active').length}
              </span>
            )}
            {s.id === 'underperforming' && underperforming.length > 0 && (
              <span className="ml-1 bg-rose-600 text-white text-[10px] rounded-full px-1.5 py-0.5 font-bold">
                {underperforming.length}
              </span>
            )}
          </button>
        ))}
      </nav>

      {/* Main Content */}
      <main className="flex-1 w-full max-w-7xl mx-auto px-6 py-8">

        {/* ── Screen 1: FSI Heatmap ─────────────────────────────────────────── */}
        {activeScreen === 'fsi' && (
          <section id="screen-fsi" className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold text-text-primary">FSI Heatmap</h2>
              <p className="text-text-muted text-sm mt-1">Facility Stress Index across all facilities in <span className="text-brand-primary font-mono">{districtCode}</span>.</p>
            </div>

            {fsiData ? (
              <>
                {/* AI Recommendation Module */}
                {aiState !== 'dismissed' && (
                  <div className={`bg-glass-bg backdrop-blur-md border ${aiState === 'applied' ? 'border-brand-accent/50 ring-brand-accent/50' : 'border-glass-border shadow-tactical-glow'} rounded-3xl p-6 mb-6 relative overflow-hidden group transition-all duration-500`}>
                    <div className="absolute inset-0 bg-gradient-to-r from-brand-primary/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
                    <div className="flex items-center gap-3 mb-4">
                      <div className={`h-8 w-8 rounded-lg ${aiState === 'applied' ? 'bg-emerald-600/20' : 'bg-violet-600/20'} flex items-center justify-center`}>
                        <span className={`text-lg ${aiState === 'active' ? 'text-violet-600 dark:text-violet-400 animate-pulse' : aiState === 'applying' ? 'text-violet-600 dark:text-violet-400 animate-spin' : 'text-emerald-600 dark:text-emerald-400'}`}>
                          {aiState === 'applying' ? '⏳' : aiState === 'applied' ? '✅' : '✨'}
                        </span>
                      </div>
                      <h3 className="text-lg font-bold text-text-primary dark:text-white">
                        {aiState === 'applying' ? 'Applying Recommendations...' : aiState === 'applied' ? 'Recommendations Applied' : 'AI Resource Recommendations'}
                      </h3>
                    </div>

                    {aiState === 'active' && (
                      <>
                        <div className="text-sm text-text-muted dark:text-slate-300 space-y-2">
                          <p className="flex items-start gap-2">
                            <span className="text-violet-500">•</span>
                            <span>Recommend shifting 2 ambulances to <span className="text-violet-300 font-semibold">North Sector</span> based on predicted FSI surge.</span>
                          </p>
                          <p className="flex items-start gap-2">
                            <span className="text-violet-500">•</span>
                            <span>Staffing levels at <span className="text-violet-300 font-semibold">East Clinic</span> are expected to fall below minimum thresholds tomorrow.</span>
                          </p>
                        </div>
                        <div className="mt-5 flex gap-3">
                          <button onClick={handleApplyAI} className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-xs font-bold rounded-xl transition shadow-lg shadow-violet-500/20">Apply Recommendations</button>
                          <button onClick={handleDismissAI} className="px-4 py-2 bg-surface dark:bg-slate-800 hover:bg-slate-700 text-text-muted dark:text-slate-300 text-xs font-bold rounded-xl transition">Dismiss</button>
                        </div>
                      </>
                    )}

                    {aiState === 'applied' && (
                      <div className="text-sm text-emerald-800/80 dark:text-emerald-300/80">
                        <p>Resources have been successfully optimized across the district.</p>
                      </div>
                    )}
                  </div>
                )}

                 {/* Summary bar */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-surface-alt dark:bg-slate-900/50 border border-glass-border dark:border-slate-800 rounded-2xl p-4 text-center">
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">Total Facilities</div>
                    <div id="fsi-total-facilities" className="text-3xl font-extrabold text-text-primary dark:text-white mt-1">
                      {isLoading ? (
                        <span className="inline-block h-8 w-10 bg-text-muted/20 animate-pulse rounded-md" />
                      ) : (
                        fsiData.facilities.length
                      )}
                    </div>
                  </div>
                  <div className="bg-surface-alt dark:bg-slate-900/50 border border-glass-border dark:border-slate-800 rounded-2xl p-4 text-center">
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">District Avg FSI</div>
                    <div id="fsi-avg-value" className="text-3xl font-extrabold mt-1" style={{ color: fsiColor(fsiData.average_fsi).bar }}>
                      {isLoading ? (
                        <span className="inline-block h-8 w-28 bg-text-muted/20 animate-pulse rounded-md" />
                      ) : (
                        fsiData.average_fsi.toFixed(6)
                      )}
                    </div>
                  </div>
                  <div className="bg-surface-alt dark:bg-slate-900/50 border border-glass-border dark:border-slate-800 rounded-2xl p-4 text-center">
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">Critical Facilities</div>
                    <div className="text-3xl font-extrabold text-rose-600 dark:text-rose-400 mt-1">
                      {isLoading ? (
                        <span className="inline-block h-8 w-10 bg-text-muted/20 animate-pulse rounded-md" />
                      ) : (
                        fsiData.facilities.filter(f => f.fsi_value > 0.001).length
                      )}
                    </div>
                  </div>
                  <div className="bg-surface-alt dark:bg-slate-900/50 border border-glass-border dark:border-slate-800 rounded-2xl p-4 text-center">
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">Normal Facilities</div>
                    <div className="text-3xl font-extrabold text-emerald-600 dark:text-emerald-400 mt-1">
                      {isLoading ? (
                        <span className="inline-block h-8 w-10 bg-text-muted/20 animate-pulse rounded-md" />
                      ) : (
                        fsiData.facilities.filter(f => f.fsi_value <= 0.0005).length
                      )}
                    </div>
                  </div>
                </div>

                 {/* Heatmap grid + summary sidebar */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                  {/* Left Column: Facility Cards */}
                  <div className="lg:col-span-8 space-y-4">
                    <div id="fsi-heatmap-grid" className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {fsiData.facilities.map(f => {
                        const col = fsiColor(f.fsi_value);
                        const pct = Math.min(100, (f.fsi_value / 0.002) * 100);
                        return (
                          <Card
                            key={f.facility_id}
                            className="bg-surface-alt dark:bg-slate-900/50 border border-glass-border dark:border-slate-800 rounded-2xl p-5 space-y-3 hover:border-slate-600 transition"
                          >
                            <div className="flex justify-between items-start">
                              <div className="flex items-center gap-2">
                                <span className={f.fsi_value > 0.001 ? "text-rose-600 dark:text-rose-400" : f.fsi_value > 0.0005 ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"}>
                                  {f.fsi_value > 0.001 ? "⚠️" : f.fsi_value > 0.0005 ? "⚡" : "✨"}
                                </span>
                                <div className="font-semibold text-text-primary dark:text-white text-sm">{f.facility_name}</div>
                              </div>
                              <Badge color={f.fsi_value > 0.001 ? "red" : f.fsi_value > 0.0005 ? "yellow" : "emerald"}>
                                {col.label}
                              </Badge>
                            </div>
                            {/* Bar */}
                            <ProgressBar value={pct} color={f.fsi_value > 0.001 ? "red" : f.fsi_value > 0.0005 ? "yellow" : "emerald"} className="mt-2" />
                            <div className="flex justify-between text-xs text-text-muted dark:text-slate-400 mt-2">
                              <span>FSI</span>
                              <span id={`fsi-val-${f.facility_id}`} className="font-mono font-bold" style={{ color: col.bar }}>
                                {isLoading ? (
                                  <span className="inline-block h-4 w-20 bg-text-muted/20 animate-pulse rounded-md" />
                                ) : (
                                  f.fsi_value.toFixed(6)
                                )}
                              </span>
                            </div>
                            <div className="text-[10px] text-slate-500 dark:text-slate-450 pt-2 flex justify-between border-t border-glass-border/40 dark:border-slate-800/40">
                              <span>Status: {f.fsi_value > 0.001 ? "High Load" : f.fsi_value > 0.0005 ? "Medium Load" : "Nominal"}</span>
                              <span>Sync: Active</span>
                            </div>
                          </Card>
                        );
                      })}
                    </div>
                  </div>

                  {/* Right Column: Status Summary Panel */}
                  <div className="lg:col-span-4">
                    <Card className="bg-surface-alt dark:bg-slate-900/50 border border-glass-border dark:border-slate-800 rounded-2xl p-6 space-y-4 shadow-xl">
                      <div>
                        <h3 className="font-bold text-text-primary dark:text-white text-base">District Status Summary</h3>
                        <p className="text-text-muted text-xs mt-0.5">Real-time indicators & benchmarks.</p>
                      </div>
                      <div className="space-y-4 text-xs">
                        <div className="flex justify-between items-center py-2 border-b border-glass-border dark:border-slate-800">
                          <span className="text-slate-500">Last Updated</span>
                          <span className="font-semibold text-text-primary dark:text-slate-200">Just now</span>
                        </div>
                        <div className="flex justify-between items-center py-2 border-b border-glass-border dark:border-slate-800">
                          <span className="text-slate-500">District Code</span>
                          <span className="font-mono text-text-primary dark:text-slate-200">{fsiData.district_code}</span>
                        </div>
                        <div className="flex justify-between items-center py-2 border-b border-glass-border dark:border-slate-800">
                          <span className="text-slate-500">Overall FSI Alert</span>
                          <Badge color={fsiData.average_fsi > 0.001 ? "red" : fsiData.average_fsi > 0.0005 ? "yellow" : "emerald"}>
                            {fsiData.average_fsi > 0.001 ? "CRITICAL" : fsiData.average_fsi > 0.0005 ? "WARNING" : "HEALTHY"}
                          </Badge>
                        </div>
                        <div className="flex justify-between items-center py-2">
                          <span className="text-slate-500">Active Recommendations</span>
                          <span className="font-semibold text-text-primary dark:text-slate-200">
                            {aiState === 'active' ? '2 pending' : aiState === 'applied' ? 'Applied' : 'None'}
                          </span>
                        </div>
                      </div>
                    </Card>
                  </div>
                </div>
              </>
            ) : (
              <div className="text-center text-slate-500 italic py-16">Loading FSI data…</div>
            )}
          </section>
        )}

        {/* ── Screen 2: Underperforming Flags ──────────────────────────────── */}
        {activeScreen === 'underperforming' && (
          <section id="screen-underperforming" className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold text-text-primary dark:text-white">Underperforming Facility Flags</h2>
              <p className="text-text-muted dark:text-slate-400 text-sm mt-1">Facilities breaching FSI or attendance thresholds. Click to drill down.</p>
            </div>

            {/* Drill-down modal */}
            {drillFacility && (
              <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setDrillFacility(null)}>
                <div className="bg-surface-alt dark:bg-slate-900 border border-slate-700 rounded-3xl p-6 max-w-md w-full shadow-2xl" onClick={e => e.stopPropagation()}>
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <h3 className="font-bold text-text-primary dark:text-white text-lg">{drillFacility.facility_name}</h3>
                      <p className="text-xs text-text-muted dark:text-slate-400 uppercase">{drillFacility.facility_type} · Drill-down</p>
                    </div>
                    <button onClick={() => setDrillFacility(null)} className="text-slate-500 hover:text-white text-lg">✕</button>
                  </div>
                  <div className="space-y-3">
                    {drillFacility.triggers.map((t, i) => (
                      <div key={i} className="bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/40 rounded-2xl p-4">
                        <div className="flex justify-between items-center mb-1">
                          <span className="text-xs font-bold text-rose-800 dark:text-rose-300 uppercase tracking-wider">{t.metric}</span>
                          <span className="font-mono text-sm text-text-primary dark:text-white">{typeof t.value === 'number' ? t.value.toFixed(4) : t.value}</span>
                        </div>
                        <p className="text-xs text-text-muted dark:text-slate-400">{t.detail}</p>
                        <div className="mt-2 text-[10px] text-rose-600/70 dark:text-rose-400/70">Threshold: {t.threshold}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {underperforming.length > 0 ? (
              <div id="underperforming-list" className="space-y-4">
                {underperforming.map(f => (
                  <div
                    key={f.facility_id}
                    className="bg-surface-alt dark:bg-slate-900/50 border border-rose-900/40 rounded-2xl p-5 hover:border-rose-700/60 transition cursor-pointer"
                    onClick={() => setDrillFacility(f)}
                  >
                    <div className="flex justify-between items-center">
                      <div>
                        <div className="font-semibold text-text-primary dark:text-white">{f.facility_name}</div>
                        <div className="text-xs text-slate-500 mt-0.5">{f.facility_type}</div>
                      </div>
                      <div className="flex gap-2 items-center">
                        {f.triggers.map((t, i) => (
                          <span key={i} className="text-[10px] bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-900/40 text-rose-800 dark:text-rose-300 px-2 py-0.5 rounded-full font-bold uppercase">
                            {t.metric}
                          </span>
                        ))}
                        <span className="text-xs text-slate-500 ml-2">→ Drill down</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-16">
                <div className="text-5xl mb-4">✅</div>
                <div id="no-flags-message" className="text-text-muted dark:text-slate-400 text-sm">No underperforming facilities in <span className="text-violet-700 dark:text-violet-300 font-mono">{districtCode}</span>.</div>
              </div>
            )}
          </section>
        )}

        {/* ── Screen 3: Redistribution Requests ────────────────────────────── */}
        {activeScreen === 'redistribution' && (
          <section id="screen-redistribution" className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold text-text-primary dark:text-white">Redistribution Requests</h2>
              <p className="text-text-muted dark:text-slate-400 text-sm mt-1">Pending resource requests from PHC In-charges in your district.</p>
            </div>

            {actionMsg && (
              <div id="redistribution-action-message" className={`px-4 py-3 rounded-2xl text-xs border ${actionMsg.includes('Error') ? 'bg-rose-50 dark:bg-rose-950/20 border-rose-200 dark:border-rose-900/40 text-rose-800 dark:text-rose-300' : 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-900/40 text-emerald-800 dark:text-emerald-300'}`}>
                {actionMsg}
              </div>
            )}

            {redistRequests.length > 0 ? (
              <div id="redistribution-requests-list" className="space-y-4">
                {redistRequests.map(r => (
                  <div key={r.alert_id} className="bg-surface-alt dark:bg-slate-900/50 border border-glass-border dark:border-slate-800 rounded-2xl p-5">
                    <div className="flex justify-between items-start gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <span className="font-semibold text-text-primary dark:text-white">{r.facility_name}</span>
                          <span className={`text-[10px] font-bold uppercase tracking-wider border px-2 py-0.5 rounded-full ${r.status === 'active' ? 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-800/40 text-amber-800 dark:text-amber-300' :
                              r.status === 'approved' ? 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-800/40 text-emerald-800 dark:text-emerald-300' :
                                'bg-rose-50 dark:bg-rose-500/10 border-rose-200 dark:border-rose-800/40 text-rose-800 dark:text-rose-300'
                            }`}>
                            {r.status}
                          </span>
                        </div>
                        <p className="text-xs text-text-muted dark:text-slate-400 leading-relaxed">{r.description}</p>
                        <p className="text-[10px] text-slate-600 mt-2">{r.created_at ? new Date(r.created_at).toLocaleString('en-IN') : ''}</p>
                      </div>

                      {r.status === 'active' && (
                        <div className="flex gap-2 shrink-0">
                          <button
                            id={`approve-btn-${r.alert_id}`}
                            onClick={() => handleRedistAction(r.alert_id, 'approved')}
                            className="px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider bg-emerald-50 dark:bg-emerald-600/20 hover:bg-emerald-100 dark:hover:bg-emerald-600/40 border border-emerald-200 dark:border-emerald-700/40 text-emerald-700 dark:text-emerald-300 transition"
                          >
                            Approve
                          </button>
                          <button
                            id={`reject-btn-${r.alert_id}`}
                            onClick={() => handleRedistAction(r.alert_id, 'rejected')}
                            className="px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider bg-rose-50 dark:bg-rose-600/20 hover:bg-rose-100 dark:hover:bg-rose-600/40 border border-rose-200 dark:border-rose-700/40 text-rose-700 dark:text-rose-300 transition"
                          >
                            Reject
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-16 text-slate-500 italic">No redistribution requests for this district.</div>
            )}
          </section>
        )}

        {/* ── Screen 4: Attendance Deviation ───────────────────────────────── */}
        {activeScreen === 'attendance' && (
          <section id="screen-attendance" className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold text-text-primary dark:text-white">Attendance Deviation Report</h2>
              <p className="text-text-muted dark:text-slate-400 text-sm mt-1">Staff present today vs sanctioned strength across all facilities.</p>
            </div>

            {attendance.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-glass-border dark:border-slate-800 text-slate-500 uppercase tracking-wider text-[10px]">
                      <th className="py-3 pr-4">Facility</th>
                      <th className="py-3 pr-4">Type</th>
                      <th className="py-3 pr-4 text-right">Sanctioned</th>
                      <th className="py-3 pr-4 text-right">Present</th>
                      <th className="py-3 pr-4 text-right">Deviation</th>
                      <th className="py-3 text-right">Attendance %</th>
                    </tr>
                  </thead>
                  <tbody id="attendance-deviation-table">
                    {attendance.map(f => (
                      <tr key={f.facility_id} className="border-b border-glass-border dark:border-slate-900/50 hover:bg-surface-alt dark:bg-slate-900/20">
                        <td className="py-3.5 pr-4 font-semibold text-text-primary dark:text-white">{f.facility_name}</td>
                        <td className="py-3.5 pr-4 text-text-muted dark:text-slate-400">{f.facility_type}</td>
                        <td className="py-3.5 pr-4 text-right font-mono text-text-muted dark:text-slate-300">
                          {isLoading ? (
                            <span className="inline-block h-4 w-8 bg-text-muted/20 animate-pulse rounded-md" />
                          ) : (
                            f.sanctioned_staff
                          )}
                        </td>
                        <td className="py-3.5 pr-4 text-right font-mono">
                          <span className={f.present_today < f.sanctioned_staff ? 'text-amber-700 dark:text-amber-300' : 'text-emerald-700 dark:text-emerald-300'}>
                            {isLoading ? (
                              <span className="inline-block h-4 w-8 bg-text-muted/20 animate-pulse rounded-md" />
                            ) : (
                              f.present_today
                            )}
                          </span>
                        </td>
                        <td className="py-3.5 pr-4 text-right font-mono">
                          <span className={f.deviation > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'}>
                            {isLoading ? (
                              <span className="inline-block h-4 w-8 bg-text-muted/20 animate-pulse rounded-md" />
                            ) : (
                              f.deviation > 0 ? `−${f.deviation}` : `+${Math.abs(f.deviation)}`
                            )}
                          </span>
                        </td>
                        <td className="py-3.5 text-right">
                          <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${f.attendance_pct < 60 ? 'bg-rose-50 dark:bg-rose-950/40 text-rose-800 dark:text-rose-300' :
                              f.attendance_pct < 80 ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300' :
                                'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-300'
                            }`}>
                            {isLoading ? (
                              <span className="inline-block h-3.5 w-10 bg-text-muted/20 animate-pulse rounded-md align-middle" />
                            ) : (
                              `${f.attendance_pct}%`
                            )}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-16 text-slate-500 italic">Loading attendance data…</div>
            )}
          </section>
        )}

        {/* ── Screen 5: Fleet Status ────────────────────────────────────────── */}
        {activeScreen === 'fleet' && (
          <section id="screen-fleet" className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold text-text-primary dark:text-white">Ambulance & Dispatch Fleet Status</h2>
              <p className="text-text-muted dark:text-slate-400 text-sm mt-1">Live dispatch status across all facilities in <span className="text-violet-700 dark:text-violet-300 font-mono">{districtCode}</span>.</p>
            </div>

            {fleet ? (
              <>
                {/* Summary pills */}
                <div className="flex gap-4 flex-wrap">
                  {[
                    { key: 'pending', label: 'Pending', color: 'amber', count: fleet.pending.length },
                    { key: 'enroute', label: 'En Route', color: 'blue', count: fleet.enroute.length },
                    { key: 'arrived', label: 'Arrived', color: 'emerald', count: fleet.arrived.length },
                  ].map(s => (
                    <div key={s.key} className={`bg-surface-alt dark:bg-slate-900/50 border rounded-2xl px-6 py-4 flex gap-3 items-center border-${s.color}-900/40`}>
                      <span className={`text-3xl font-extrabold text-${s.color}-400`}>{s.count}</span>
                      <span className="text-xs text-text-muted dark:text-slate-400 uppercase tracking-wider font-semibold">{s.label}</span>
                    </div>
                  ))}
                  <div className="bg-surface-alt dark:bg-slate-900/50 border border-glass-border dark:border-slate-800 rounded-2xl px-6 py-4 flex gap-3 items-center">
                    <span className="text-3xl font-extrabold text-text-muted dark:text-slate-300">{fleet.total}</span>
                    <span className="text-xs text-text-muted dark:text-slate-400 uppercase tracking-wider font-semibold">Total</span>
                  </div>
                </div>

                {/* Three columns */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  {[
                    { key: 'pending' as const, label: '🟡 Pending', color: 'amber' },
                    { key: 'enroute' as const, label: '🔵 En Route', color: 'blue' },
                    { key: 'arrived' as const, label: '🟢 Arrived', color: 'emerald' },
                  ].map(col => (
                    <div key={col.key}>
                      <h3 className="text-sm font-bold text-text-muted dark:text-slate-300 mb-3">{col.label}</h3>
                      <div id={`fleet-${col.key}-list`} className="space-y-3">
                        {fleet[col.key].length === 0 ? (
                          <div className="text-slate-600 text-xs italic text-center py-4">None</div>
                        ) : (
                          fleet[col.key].map(d => (
                            <div key={d.dispatch_id} className={`bg-surface-alt dark:bg-slate-900/50 border border-${col.color}-900/30 rounded-xl p-4`}>
                              <div className="font-semibold text-sm text-text-primary dark:text-white">{d.facility_name}</div>
                              {d.symptom && <div className="text-xs text-text-muted dark:text-slate-400 mt-1 truncate">{d.symptom}</div>}
                              {d.eta && <div className="text-[10px] text-slate-500 mt-1.5">ETA: {new Date(d.eta).toLocaleTimeString('en-IN')}</div>}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="text-center py-16 text-slate-500 italic">Loading fleet data…</div>
            )}
          </section>
        )}

        {/* ── Screen 6: Benchmarks ──────────────────────────────────────────── */}
        {activeScreen === 'benchmarks' && (
          <section id="screen-benchmarks" className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold text-text-primary dark:text-white">Benchmark Comparison View</h2>
              <p className="text-text-muted dark:text-slate-400 text-sm mt-1">Live district metrics vs NFHS / Census / data.gov.in reference baselines.</p>
            </div>

            {benchmarks ? (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Live vs Reference cards */}
                <div className="bg-surface-alt dark:bg-slate-900/50 border border-glass-border dark:border-slate-800 rounded-3xl p-6 space-y-5">
                  <h3 className="text-sm font-bold text-violet-700 dark:text-violet-300 uppercase tracking-wider">Live District Metrics</h3>
                  <div className="space-y-3">
                    {[
                      { label: 'Average FSI', value: benchmarks.live_metrics.avg_fsi.toFixed(6) },
                      { label: 'Total Sanctioned Staff', value: benchmarks.live_metrics.total_sanctioned_staff },
                      { label: 'Staff Present Today', value: benchmarks.live_metrics.total_staff_present_today },
                      { label: 'Attendance %', value: `${benchmarks.live_metrics.attendance_pct}%` },
                      { label: 'Total Facilities', value: benchmarks.total_facilities },
                    ].map(row => (
                      <div key={row.label} className="flex justify-between items-center text-sm border-b border-glass-border dark:border-slate-900 pb-2">
                        <span className="text-text-muted dark:text-slate-400">{row.label}</span>
                        <span id={`bm-live-${row.label.replace(/\s+/g, '-').toLowerCase()}`} className="font-mono font-bold text-text-primary dark:text-white">
                          {isLoading ? (
                            <span className="inline-block h-4 w-16 bg-text-muted/20 animate-pulse rounded-md" />
                          ) : (
                            row.value
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="space-y-6">
                  {/* Census Reference */}
                  <div className="bg-surface-alt dark:bg-slate-900/50 border border-indigo-900/40 rounded-3xl p-5 space-y-3">
                    <h3 className="text-sm font-bold text-indigo-700 dark:text-indigo-300 uppercase tracking-wider">Census Reference</h3>
                    {[
                      { label: 'Catchment Population', value: benchmarks.census_reference.catchment_population?.toLocaleString('en-IN') ?? '—' },
                      { label: 'Age < 5 Cohort', value: `${((benchmarks.census_reference.age_cohort_under_5 ?? 0) * 100).toFixed(1)}%` },
                      { label: 'Age > 60 Cohort', value: `${((benchmarks.census_reference.age_cohort_over_60 ?? 0) * 100).toFixed(1)}%` },
                    ].map(row => (
                      <div key={row.label} className="flex justify-between text-xs">
                        <span className="text-slate-500">{row.label}</span>
                        <span id={`bm-census-${row.label.replace(/\s+/g, '-').toLowerCase()}`} className="font-mono text-indigo-700 dark:text-indigo-300">
                          {isLoading ? (
                            <span className="inline-block h-3.5 w-16 bg-text-muted/20 animate-pulse rounded-md" />
                          ) : (
                            row.value
                          )}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* NFHS Reference */}
                  <div className="bg-surface-alt dark:bg-slate-900/50 border border-teal-900/40 rounded-3xl p-5 space-y-3">
                    <h3 className="text-sm font-bold text-teal-300 uppercase tracking-wider">NFHS Reference</h3>
                    {[
                      { label: 'Seasonal Risk Weight', value: benchmarks.nfhs_reference.seasonal_vector_weight ?? '—' },
                      { label: 'Disease Burden', value: benchmarks.nfhs_reference.disease_burden_indicators ?? '—' },
                    ].map(row => (
                      <div key={row.label} className="flex justify-between text-xs">
                        <span className="text-slate-500">{row.label}</span>
                        <span id={`bm-nfhs-${row.label.replace(/\s+/g, '-').toLowerCase()}`} className="font-mono text-teal-300">
                          {isLoading ? (
                            <span className="inline-block h-3.5 w-16 bg-text-muted/20 animate-pulse rounded-md" />
                          ) : (
                            String(row.value)
                          )}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* data.gov.in comparison */}
                  <div className="bg-surface-alt dark:bg-slate-900/50 border border-violet-900/40 rounded-3xl p-5 space-y-3">
                    <h3 className="text-sm font-bold text-violet-700 dark:text-violet-300 uppercase tracking-wider">data.gov.in Comparison</h3>
                    <div className="space-y-3">
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-500">Benchmark Staff Count</span>
                        <span className="font-mono text-text-muted dark:text-slate-300">
                          {isLoading ? (
                            <span className="inline-block h-3.5 w-10 bg-text-muted/20 animate-pulse rounded-md" />
                          ) : (
                            benchmarks.datagovin_reference.sanctioned_staff_count ?? '—'
                          )}
                        </span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-500">Actual Staff Count</span>
                        <span id="bm-actual-staff" className="font-mono text-text-primary dark:text-white">
                          {isLoading ? (
                            <span className="inline-block h-3.5 w-10 bg-text-muted/20 animate-pulse rounded-md" />
                          ) : (
                            benchmarks.comparison.staff_vs_benchmark.actual
                          )}
                        </span>
                      </div>
                      <div className={`flex justify-between text-xs font-bold ${benchmarks.comparison.staff_vs_benchmark.gap < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                        <span>Gap vs Benchmark</span>
                        <span id="bm-staff-gap">
                          {isLoading ? (
                            <span className="inline-block h-3.5 w-10 bg-text-muted/20 animate-pulse rounded-md" />
                          ) : (
                            `${benchmarks.comparison.staff_vs_benchmark.gap > 0 ? '+' : ''}${benchmarks.comparison.staff_vs_benchmark.gap}`
                          )}
                        </span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-500">Supply Lead Time Baseline</span>
                        <span className="font-mono text-text-muted dark:text-slate-300">
                          {isLoading ? (
                            <span className="inline-block h-3.5 w-10 bg-text-muted/20 animate-pulse rounded-md" />
                          ) : (
                            benchmarks.datagovin_reference.supply_lead_time_baseline ?? '—'
                          )} days</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-16 text-slate-500 italic">Loading benchmark data…</div>
            )}
          </section>
        )}
      </main>

      <footer className="w-full text-center py-8 text-xs text-slate-600 border-t border-glass-border dark:border-slate-900 mt-12 z-10" suppressHydrationWarning>
        PulseDesk © {new Date().getFullYear()} • Made by Team Codecraft
      </footer>
    </div>
  );
}
