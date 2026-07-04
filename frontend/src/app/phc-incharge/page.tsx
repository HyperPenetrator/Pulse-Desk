'use client';

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';

export default function PHCInchargeDashboard() {
  const [token, setToken] = useState<string | null>(null);
  const [facilityId, setFacilityId] = useState<string | null>(null);
  const [facilities, setFacilities] = useState<any[]>([]);
  const [selectedFacility, setSelectedFacility] = useState<string>('');

  // Dashboard data
  const [dashboardData, setDashboardData] = useState<any | null>(null);
  const [inventory, setInventory] = useState<any[]>([]);
  const [attendanceData, setAttendanceData] = useState<any | null>(null);
  const [fsiData, setFsiData] = useState<any | null>(null);

  const [loadingData, setLoadingData] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Redistribution form states
  const [redistributionReason, setRedistributionReason] = useState('');
  const [submittingRedistribution, setSubmittingRedistribution] = useState(false);
  const [redistributionMessage, setRedistributionMessage] = useState<string | null>(null);

  const derivedPresentCount = attendanceData?.attendance
    ? attendanceData.attendance.filter((s: any) => s.status === 'Present').length
    : 0;

  const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // Fetch facilities for login selector
  useEffect(() => {
    fetch(`${backendUrl}/api/v1/facilities`)
      .then((res) => res.json())
      .then((data) => {
        setFacilities(data);
        if (data.length > 0) {
          setSelectedFacility(data[0].id);
        }
      })
      .catch((err) => console.error('Error fetching facilities:', err));
  }, [backendUrl]);

  // Load token from localStorage on mount
  useEffect(() => {
    const savedToken = localStorage.getItem('token');
    const savedFacilityId = localStorage.getItem('facility_id');
    if (savedToken && savedFacilityId) {
      setToken(savedToken);
      setFacilityId(savedFacilityId);
    }
  }, []);

  // Poll dashboard data when logged in
  useEffect(() => {
    if (!token || !facilityId) return;

    setIsLoading(true);
    const fetchData = async () => {
      try {
        const headers = { Authorization: `Bearer ${token}` };

        // 1. Fetch main dashboard data (reused from receptionist endpoint structure or similar)
        const dbResp = await fetch(`${backendUrl}/api/v1/receptionist/data/${facilityId}`, { headers });
        if (!dbResp.ok) {
          if (dbResp.status === 401 || dbResp.status === 403) {
            handleLogout();
            throw new Error('Session expired or unauthorized');
          }
          throw new Error('Failed to fetch dashboard data');
        }
        const dbData = await dbResp.json();
        setDashboardData(dbData);

        // 2. Fetch inventory wired to /api/v1/inventory/{facility_id}
        const invResp = await fetch(`${backendUrl}/api/v1/inventory/${facilityId}`, { headers });
        if (invResp.ok) {
          const invData = await invResp.json();
          setInventory(invData);
        }

        // 3. Fetch staff attendance wired to /api/v1/attendance/{facility_id}
        const attResp = await fetch(`${backendUrl}/api/v1/attendance/${facilityId}`, { headers });
        if (attResp.ok) {
          const attData = await attResp.json();
          setAttendanceData(attData);
        }

        // 4. Fetch FSI gauge data wired to /api/v1/fsi/{facility_id}
        const fsiResp = await fetch(`${backendUrl}/api/v1/fsi/${facilityId}`, { headers });
        if (fsiResp.ok) {
          const fData = await fsiResp.json();
          setFsiData(fData);
        }

        setError(null);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 3000); // Poll every 3 seconds

    return () => clearInterval(interval);
  }, [token, facilityId, backendUrl]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const response = await fetch(`${backendUrl}/api/v1/auth/mock-login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          role: 'phc_incharge',
          facility_id: selectedFacility,
        }),
      });

      if (!response.ok) {
        throw new Error('Login failed');
      }

      const data = await response.json();
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('facility_id', selectedFacility);
      setToken(data.access_token);
      setFacilityId(selectedFacility);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('facility_id');
    setToken(null);
    setFacilityId(null);
    setDashboardData(null);
    setInventory([]);
    setAttendanceData(null);
    setFsiData(null);
  };

  const handleAlertAction = async (dispatchId: string, status: 'enroute' | 'arrived') => {
    try {
      const response = await fetch(`${backendUrl}/api/v1/dispatch/${dispatchId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ status }),
      });

      if (!response.ok) {
        throw new Error('Failed to update dispatch status');
      }

      // Optimistically update status
      if (dashboardData) {
        const updatedDispatches = dashboardData.active_dispatches.map((d: any) =>
          d.id === dispatchId ? { ...d, status } : d
        ).filter((d: any) => d.status !== 'arrived');
        setDashboardData({ ...dashboardData, active_dispatches: updatedDispatches });
      }
    } catch (err: any) {
      alert(`Error updating dispatch: ${err.message}`);
    }
  };

  const handleRedistributionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!redistributionReason.trim()) {
      setRedistributionMessage('Please enter a reason for redistribution.');
      return;
    }
    setSubmittingRedistribution(true);
    setRedistributionMessage(null);
    try {
      const response = await fetch(`${backendUrl}/api/v1/redistribution`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          facility_id: facilityId,
          reason: redistributionReason,
        }),
      });

      if (!response.ok) {
        throw new Error('Redistribution request failed');
      }

      const data = await response.json();
      setRedistributionMessage('Redistribution request submitted successfully!');
      setRedistributionReason('');
    } catch (err: any) {
      setRedistributionMessage(`Error: ${err.message}`);
    } finally {
      setSubmittingRedistribution(false);
    }
  };

  const handleToggleAttendance = async (staffId: string, newPresent: boolean) => {
    if (!token || !facilityId || !attendanceData) return;

    const previousAttendanceData = { ...attendanceData };

    // Optimistically update status in state
    const updatedAttendance = attendanceData.attendance.map((s: any) =>
      s.staff_id === staffId ? { ...s, status: newPresent ? 'Present' : 'Absent' } : s
    );

    const newPresentCount = updatedAttendance.filter((s: any) => s.status === 'Present').length;

    setAttendanceData({
      ...attendanceData,
      present_count: newPresentCount,
      attendance: updatedAttendance
    });

    try {
      const response = await fetch(`${backendUrl}/api/v1/attendance/${facilityId}/${staffId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ present: newPresent })
      });

      if (!response.ok) {
        throw new Error('Failed to update attendance');
      }
    } catch (err) {
      // Revert on request failure
      setAttendanceData(previousAttendanceData);
      alert('Error updating attendance. Restoring previous state.');
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-surface text-text-primary flex flex-col items-center justify-center p-6 selection:bg-brand-primary/20">
        <div className="absolute top-0 left-0 right-0 h-[400px] bg-gradient-to-b from-brand-primary/10 via-transparent to-transparent pointer-events-none" />

        <div className="w-full max-w-md bg-glass-bg backdrop-blur-md border border-glass-border rounded-3xl p-8 shadow-glass-dark relative z-10">
          <div className="flex flex-col items-center mb-8">
            <div className="h-12 w-12 rounded-2xl bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-500/20 mb-4">
              <svg className="w-6 h-6 text-slate-950" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-text-primary">
              PulseDesk
            </h1>
            <p className="text-xs text-text-muted mt-1 uppercase tracking-widest">PHC In-charge Login</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-6">
            <div className="space-y-2">
              <label htmlFor="facility-select" className="block text-xs font-semibold uppercase tracking-wider text-text-muted dark:text-slate-400">
                Select Your Facility
              </label>
              <select
                id="facility-select"
                className="w-full bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-2xl px-4 py-3 text-text-primary dark:text-slate-100 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
                value={selectedFacility}
                onChange={(e) => setSelectedFacility(e.target.value)}
              >
                {facilities.map((fac) => (
                  <option key={fac.id} value={fac.id}>
                    {fac.name} ({fac.type})
                  </option>
                ))}
              </select>
            </div>

            <button
              id="login-button"
              type="submit"
              className="w-full py-4 rounded-2xl font-bold text-sm tracking-wide uppercase transition duration-200 bg-gradient-to-r from-emerald-500 to-teal-400 hover:from-emerald-400 hover:to-teal-300 text-slate-950 shadow-lg shadow-emerald-500/10"
            >
              Sign In as PHC In-charge
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface text-text-primary flex flex-col font-sans selection:bg-brand-primary/20">
      <header className="relative w-full border-b border-glass-border bg-glass-bg backdrop-blur-md px-6 py-4 flex justify-between items-center z-10 shadow-glass-light">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-500/15">
            <svg className="w-4 h-4 text-slate-950 font-bold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-text-primary">
              PulseDesk
            </h1>
            <p className="text-[9px] text-text-muted uppercase tracking-widest -mt-0.5">PHC In-charge Console</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {dashboardData && (
            <div id="logged-in-facility-badge" className="text-xs bg-surface-alt dark:bg-slate-900 border border-glass-border dark:border-slate-800 rounded-full px-3 py-1.5 text-text-muted dark:text-slate-300 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              {dashboardData.facility_name}
            </div>
          )}
          <button
            id="logout-button"
            onClick={handleLogout}
            className="text-xs bg-rose-50 dark:bg-rose-950/20 hover:bg-rose-100 dark:hover:bg-rose-950/40 border border-rose-200 dark:border-rose-900/40 text-rose-800 dark:text-rose-300 rounded-xl px-3.5 py-3 md:py-1.5 min-h-[44px] md:min-h-0 flex items-center justify-center transition"
          >
            Sign Out
          </button>
        </div>
      </header>

      {error && (
        <div className="bg-rose-50 dark:bg-rose-950/30 border-b border-rose-200 dark:border-rose-900/50 px-6 py-3 text-sm text-rose-800 dark:text-rose-300 text-center">
          ⚠️ Connection Error: {error}
        </div>
      )}

      <main className="flex-1 w-full max-w-7xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start z-10">

        {/* LEFT COLUMN: Main In-charge operations */}
        <div className="lg:col-span-8 space-y-8">

          {/* Top Row: FSI Gauge & Staffing Attendance / Alert side-by-side */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-8">
            {/* Stress level card (FSI GAUGE) - 40% (md:col-span-5) */}
            <motion.section
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.00, ease: "easeOut" }}
              className={`order-2 md:order-1 md:col-span-5 bg-glass-bg backdrop-blur-md border border-glass-border shadow-glass-dark rounded-3xl p-6 space-y-4 transition-colors duration-500 ${(fsiData?.fsi_value || 0) > 0.001 ? 'border-brand-danger/50 ring-1 ring-brand-danger/30' : ''}`}
            >
              <div>
                <h2 className="text-lg font-bold text-text-primary dark:text-white">Facility Stress Index (FSI)</h2>
                <p className="text-text-muted dark:text-slate-400 text-xs mt-0.5">Real-time daily load vs capacity.</p>
              </div>

              <div className="flex flex-col items-center justify-center py-4 space-y-3">
                <div className="relative flex items-center justify-center">
                  <svg className="w-36 h-36 transform -rotate-90">
                    <circle cx="72" cy="72" r="60" stroke="#1e293b" strokeWidth="12" fill="transparent" />
                    <circle
                      cx="72"
                      cy="72"
                      r="60"
                      stroke="url(#fsiGradient)"
                      strokeWidth="12"
                      fill="transparent"
                      strokeDasharray="377"
                      strokeDashoffset={377 - (377 * Math.min(1, fsiData?.fsi_value || 0))}
                      strokeLinecap="round"
                    />
                    <defs>
                      <linearGradient id="fsiGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#10b981" />
                        <stop offset="50%" stopColor="#f59e0b" />
                        <stop offset="100%" stopColor="#ef4444" />
                      </linearGradient>
                    </defs>
                  </svg>
                  <div className="absolute text-center">
                    <div id="fsi-value-display" className="text-3xl font-extrabold text-black flex justify-center">
                      {isLoading ? (
                        <span className="h-8 w-20 bg-text-muted/20 animate-pulse rounded-md" />
                      ) : (
                        Math.round(fsiData?.fsi_value || 0)
                      )}
                    </div>
                    <div className="text-[10px] text-text-muted dark:text-slate-400 font-bold uppercase tracking-wider mt-1">Stress Level</div>
                  </div>
                </div>

                <div className="text-xs text-text-muted dark:text-slate-300 grid grid-cols-2 gap-x-6 gap-y-2 w-full pt-4 border-t border-glass-border dark:border-slate-900">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Footfall today:</span>
                    <span id="fsi-footfall" className="font-bold text-text-primary dark:text-white">
                      {isLoading ? (
                        <span className="inline-block h-4 w-12 bg-text-muted/20 animate-pulse rounded-md align-middle" />
                      ) : (
                        fsiData?.real_time_daily_footfall || 0
                      )}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Catchment Pop:</span>
                    <span id="fsi-population" className="font-bold text-text-primary dark:text-white">
                      {isLoading ? (
                        <span className="inline-block h-4 w-16 bg-text-muted/20 animate-pulse rounded-md align-middle" />
                      ) : (
                        fsiData?.census_catchment_population || 0
                      )}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Beds Baseline:</span>
                    <span id="fsi-beds" className="font-bold text-text-primary dark:text-white">
                      {isLoading ? (
                        <span className="inline-block h-4 w-12 bg-text-muted/20 animate-pulse rounded-md align-middle" />
                      ) : (
                        fsiData?.available_beds_baseline || 0
                      )}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Status:</span>
                    <span className={`font-bold ${(fsiData?.fsi_value || 0) > 0.001 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'
                      }`}>
                      {isLoading ? (
                        <span className="inline-block h-4 w-16 bg-text-muted/20 animate-pulse rounded-md align-middle" />
                      ) : (
                        (fsiData?.fsi_value || 0) > 0.001 ? 'High Stress' : 'Nominal'
                      )}
                    </span>
                  </div>
                </div>
              </div>
            </motion.section>

            {/* Staff Attendance Log / Alert card - 60% (md:col-span-7) */}
            <motion.section
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.05, ease: "easeOut" }}
              className={`order-1 md:order-2 md:col-span-7 bg-glass-bg backdrop-blur-md border shadow-glass-dark rounded-3xl p-6 space-y-4 transition-colors duration-500 ${(attendanceData && derivedPresentCount < attendanceData.sanctioned_staff) ? 'border-brand-danger/50 ring-1 ring-brand-danger/30' : 'border-glass-border'}`}
            >
              <div>
                <h2 className="text-lg font-bold text-text-primary">Staff Attendance Log</h2>
                <p className="text-text-muted text-xs mt-0.5">Sanctioned counts vs active today.</p>
              </div>

              {attendanceData && derivedPresentCount < attendanceData.sanctioned_staff && (
                <div className="bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/60 rounded-xl p-3 flex items-center gap-3">
                  <span className="relative flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-rose-500"></span>
                  </span>
                  <div>
                    <h3 className="text-rose-800 dark:text-rose-300 text-xs font-bold uppercase tracking-wider">Critical Staffing Alert</h3>
                    <p className="text-rose-700/80 dark:text-rose-400/80 text-[10px]">Operating below sanctioned strength. High risk of queue pileup.</p>
                  </div>
                </div>
              )}

              {attendanceData ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-surface-alt dark:bg-slate-950 border border-slate-850 p-3 rounded-2xl text-center">
                      <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold block">Sanctioned Staff</span>
                      <span id="sanctioned-staff-count" className="text-2xl font-extrabold text-text-primary dark:text-slate-100 mt-1 block">
                        {isLoading ? (
                          <span className="inline-block h-6 w-12 bg-text-muted/20 animate-pulse rounded-md" />
                        ) : (
                          attendanceData.sanctioned_staff
                        )}
                      </span>
                    </div>
                    <div className="bg-surface-alt dark:bg-slate-950 border border-slate-850 p-3 rounded-2xl text-center">
                      <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold block">Present Today</span>
                      <span id="present-staff-count" className={`text-2xl font-extrabold mt-1 block ${derivedPresentCount < attendanceData.sanctioned_staff ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'
                        }`}>
                        {isLoading ? (
                          <span className="inline-block h-6 w-12 bg-text-muted/20 animate-pulse rounded-md" />
                        ) : (
                          derivedPresentCount
                        )}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-2 max-h-[160px] overflow-y-auto pr-1">
                    {attendanceData.attendance && attendanceData.attendance.length > 0 ? (
                      attendanceData.attendance.map((staff: any) => (
                        <div key={staff.staff_id} className="flex justify-between items-center text-xs bg-surface-alt dark:bg-slate-950/60 border border-glass-border dark:border-slate-900/60 p-2 rounded-xl">
                          <div>
                            <div className="font-semibold text-text-primary dark:text-slate-200">{staff.name}</div>
                            <div className="text-[10px] text-slate-500 font-mono">{staff.role}</div>
                          </div>
                          <button
                            onClick={() => handleToggleAttendance(staff.staff_id, staff.status !== 'Present')}
                            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 ${
                              staff.status === 'Present' ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-700'
                            }`}
                          >
                            <span
                              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                                staff.status === 'Present' ? 'translate-x-5' : 'translate-x-0'
                              }`}
                            />
                          </button>
                        </div>
                      ))
                    ) : (
                      <div className="text-slate-500 text-xs italic text-center py-4">No staff records.</div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-slate-500 text-xs italic text-center py-8">Loading attendance metrics...</div>
              )}
            </motion.section>
          </div>

          {/* Beds & Facility Info 3-column Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.10, ease: "easeOut" }}
              className="bg-surface-alt dark:bg-slate-900/40 border border-glass-border dark:border-slate-800/80 rounded-3xl p-6 shadow-xl space-y-4 text-center"
            >
              <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold block">Available Beds</span>
              <span className="text-2xl font-extrabold text-text-primary dark:text-white mt-1 block">
                {isLoading ? (
                  <span className="inline-block h-6 w-12 bg-text-muted/20 animate-pulse rounded-md" />
                ) : (
                  dashboardData?.available_beds ?? 0
                )}
              </span>
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.15, ease: "easeOut" }}
              className="bg-surface-alt dark:bg-slate-900/40 border border-glass-border dark:border-slate-800/80 rounded-3xl p-6 shadow-xl space-y-4 text-center"
            >
              <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold block">Sanctioned Beds</span>
              <span className="text-2xl font-extrabold text-text-primary dark:text-white mt-1 block">
                {isLoading ? (
                  <span className="inline-block h-6 w-12 bg-text-muted/20 animate-pulse rounded-md" />
                ) : (
                  dashboardData?.sanctioned_beds ?? 0
                )}
              </span>
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.20, ease: "easeOut" }}
              className="bg-surface-alt dark:bg-slate-900/40 border border-glass-border dark:border-slate-800/80 rounded-3xl p-6 shadow-xl space-y-4 text-center"
            >
              <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold block">Facility Type</span>
              <span className="text-lg font-extrabold text-text-primary dark:text-white mt-1 block uppercase tracking-wider">
                {isLoading ? (
                  <span className="inline-block h-6 w-24 bg-text-muted/20 animate-pulse rounded-md" />
                ) : (
                  dashboardData?.facility_type ?? 'PHC'
                )}
              </span>
            </motion.div>
          </div>

          {/* INVENTORY TABLE WITH DRP reorder warning */}
          <motion.section
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.25, ease: "easeOut" }}
            className="bg-surface-alt dark:bg-slate-900/40 border border-glass-border dark:border-slate-800/80 rounded-3xl p-6 shadow-xl space-y-4"
          >
            <div>
              <h2 className="text-xl font-bold text-text-primary dark:text-white">PHC Pharmacy Inventory</h2>
              <p className="text-text-muted text-xs mt-0.5">Real-time stock runway compared against Dynamic Reorder Points (DRP).</p>
            </div>

            <div className="pt-2 space-y-3">
              {inventory && inventory.length > 0 ? (
                (() => {
                  const maxVal = Math.max(...inventory.map((i: any) => i.current_stock || 0), 100);
                  return inventory.map((item: any) => {
                    const pct = Math.min(100, Math.round(((item.current_stock || 0) / maxVal) * 100));
                    return (
                      <div key={item.id} className="flex items-center justify-between gap-4 text-xs">
                        <span className="font-semibold text-text-primary dark:text-slate-200 w-36 shrink-0">{item.medicine_name}</span>
                        <div className="flex-1 bg-slate-200 dark:bg-slate-800 h-2 rounded-full overflow-hidden">
                          <div 
                            className="bg-emerald-500 h-full rounded-full" 
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="font-mono text-text-muted w-12 text-right">{item.current_stock}</span>
                      </div>
                    );
                  });
                })()
              ) : (
                <div className="text-slate-500 text-xs italic text-center py-4">No inventory tracked.</div>
              )}
            </div>
          </motion.section>

          {/* REQUEST REDISTRIBUTION */}
          <section className="bg-surface-alt dark:bg-slate-900/40 border border-glass-border dark:border-slate-800/80 rounded-3xl p-6 shadow-xl space-y-6">
            <div>
              <h2 className="text-xl font-bold text-text-primary dark:text-white">Resource Redistribution</h2>
              <p className="text-text-muted text-xs mt-0.5">Submit an urgent request to the District Admin to transfer stock or staff due to overload.</p>
            </div>

            <form onSubmit={handleRedistributionSubmit} className="space-y-4">
              <div className="space-y-2">
                <div className="flex justify-between items-end">
                  <label htmlFor="redistribution-reason-input" className="block text-[10px] uppercase font-bold tracking-wider text-text-muted">
                    Reason for Redistribution Request
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      const shortages = inventory.filter(i => i.current_stock < i.drp_value).map(i => i.medicine_name).join(', ');
                      const staffShort = attendanceData ? (attendanceData.sanctioned_staff - derivedPresentCount) : 0;
                      let draft = `Urgent Redistribution Required.\n`;
                      if (shortages) draft += `- Critical Inventory Shortages: ${shortages} below DRP.\n`;
                      if (staffShort > 0) draft += `- Staffing Deficit: Operating with ${staffShort} staff member(s) short today.\n`;
                      if (!shortages && staffShort === 0) draft += `- Anticipated surge load based on recent footfall trends.`;
                      setRedistributionReason(draft);
                    }}
                    className="text-[10px] flex items-center justify-center gap-1.5 bg-indigo-50 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-500/30 border border-indigo-200 dark:border-indigo-500/30 rounded-lg px-2.5 py-3 md:py-1.5 transition uppercase tracking-wider font-bold min-h-[44px] md:min-h-0"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                    Auto-Fill Request
                  </button>
                </div>
                <textarea
                  id="redistribution-reason-input"
                  rows={3}
                  className="w-full bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-2xl px-4 py-3 text-sm text-text-primary dark:text-slate-100 focus:outline-none focus:border-emerald-500"
                  placeholder="Describe your current stock shortage, surge load, or staffing deficiency..."
                  value={redistributionReason}
                  onChange={(e) => setRedistributionReason(e.target.value)}
                />
              </div>

              <button
                id="request-redistribution-button"
                type="submit"
                disabled={submittingRedistribution}
                className="w-full md:w-auto px-6 py-3.5 md:py-3 rounded-xl font-bold text-xs uppercase tracking-wider bg-gradient-to-r from-emerald-500 to-teal-400 text-slate-950 hover:from-emerald-400 hover:to-teal-300 disabled:bg-surface dark:bg-slate-800 disabled:text-slate-500 transition duration-200 shadow-lg shadow-emerald-500/10 min-h-[44px] flex items-center justify-center"
              >
                {submittingRedistribution ? 'Submitting...' : 'Request Redistribution'}
              </button>
            </form>

            {redistributionMessage && (
              <div id="redistribution-status-message" className={`p-4 rounded-2xl text-xs border ${redistributionMessage.includes('Error') ? 'bg-rose-50 dark:bg-rose-950/20 border-rose-200 dark:border-rose-900/40 text-rose-800 dark:text-rose-300' : 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-900/40 text-emerald-800 dark:text-emerald-300'
                }`}>
                {redistributionMessage}
              </div>
            )}
          </section>

        </div>

        {/* RIGHT COLUMN: Live alerts & Walk-ins */}
        <div className="lg:col-span-4 space-y-8">

          {/* Bed Availability Panel */}
          <section className="bg-surface-alt dark:bg-slate-900/40 border border-glass-border dark:border-slate-800/80 rounded-3xl p-6 shadow-xl space-y-4">
            <h2 className="text-base font-bold text-text-primary dark:text-white">Bed Availability Panel</h2>
            <p className="text-text-muted dark:text-slate-400 text-xs -mt-2">Read-only facility capacity index</p>

            {dashboardData ? (
              <div className="bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-2xl p-5 space-y-4">
                <div>
                  <div className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold">Facility Name</div>
                  <div className="text-sm font-bold text-text-primary dark:text-white mt-0.5">{dashboardData.facility_name}</div>
                </div>

                <div className="grid grid-cols-2 gap-4 pt-2 border-t border-glass-border dark:border-slate-900">
                  <div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold">Available Beds</div>
                    <div id="available-beds-display" className="text-xl font-extrabold text-emerald-400 mt-0.5">
                      {dashboardData.available_beds}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold">Sanctioned Beds</div>
                    <div className="text-lg font-bold text-text-muted dark:text-slate-300 mt-0.5">
                      {dashboardData.sanctioned_beds}
                    </div>
                  </div>
                </div>

                <div className="pt-2 border-t border-glass-border dark:border-slate-900 flex justify-between items-center text-xs">
                  <span className="text-slate-500">Facility Type:</span>
                  <span className="font-bold text-text-primary dark:text-white bg-surface-alt dark:bg-slate-900 px-2 py-0.5 rounded border border-glass-border dark:border-slate-800">
                    {dashboardData.facility_type}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-slate-500 text-xs italic text-center py-6">
                Loading capacity metrics...
              </div>
            )}
          </section>

          {/* Live Dispatch Alerts Feed */}
          <section className="bg-surface-alt dark:bg-slate-900/40 border border-glass-border dark:border-slate-800/80 rounded-3xl p-6 shadow-xl space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-base font-bold text-text-primary dark:text-white">Live Dispatch Alerts</h2>
              <span className="inline-flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            </div>
            <p className="text-text-muted dark:text-slate-400 text-xs -mt-2">Incoming emergency transport alerts scoped to your facility.</p>

            <div id="dispatch-alerts-container" className="space-y-4 max-h-[300px] overflow-y-auto pr-1">
              {dashboardData?.active_dispatches && dashboardData.active_dispatches.length > 0 ? (
                dashboardData.active_dispatches.map((d: any) => (
                  <div key={d.id} className="bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-2xl p-4 space-y-3">
                    <div className="flex justify-between items-start">
                      <span className="inline-block px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-rose-50 dark:bg-rose-950 text-rose-800 dark:text-rose-300 border border-rose-200 dark:border-rose-900/30">
                        Ambulance Alert
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {d.eta ? `${new Date(d.eta).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} ETA` : 'Pending'}
                      </span>
                    </div>

                    <p className="text-text-primary dark:text-slate-200 text-xs leading-relaxed font-semibold">
                      {d.symptom}
                    </p>

                    <div className="flex items-center justify-between pt-2 border-t border-glass-border dark:border-slate-900 text-xs">
                      <div>
                        <span className="text-[10px] text-slate-500 uppercase tracking-widest block font-medium">Status</span>
                        <span className={`font-semibold capitalize ${d.status === 'enroute' ? 'text-amber-400' : 'text-rose-400'}`}>
                          {d.status}
                        </span>
                      </div>

                      <div className="flex gap-2">
                        {d.status === 'pending' && (
                          <button
                            onClick={() => handleAlertAction(d.id, 'enroute')}
                            className="acknowledge-alert-button text-[10px] bg-amber-500 text-slate-950 hover:bg-amber-400 font-bold px-2.5 py-1.5 rounded-lg transition"
                          >
                            Acknowledge
                          </button>
                        )}
                        {d.status === 'enroute' && (
                          <button
                            onClick={() => handleAlertAction(d.id, 'arrived')}
                            className="arrive-alert-button text-[10px] bg-emerald-500 text-slate-950 hover:bg-emerald-400 font-bold px-2.5 py-1.5 rounded-lg transition"
                          >
                            Mark Arrived
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-slate-500 text-xs italic text-center py-8 bg-surface-alt dark:bg-slate-950/20 border border-glass-border dark:border-slate-900 rounded-2xl">
                  No active incoming dispatches.
                </div>
              )}
            </div>
          </section>

        </div>

      </main>

      <footer className="w-full text-center py-8 text-xs text-slate-600 border-t border-glass-border dark:border-slate-900 mt-12 z-10" suppressHydrationWarning>
        PulseDesk © {new Date().getFullYear()} • Made by Team Codecraft
      </footer>
    </div>
  );
}
