'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function Home() {
  const [symptom, setSymptom] = useState('');
  const [formSubmitted, setFormSubmitted] = useState(false);
  const [latitude, setLatitude] = useState<number | null>(null);
  const [longitude, setLongitude] = useState<number | null>(null);
  const [address, setAddress] = useState('');
  const [locationMethod, setLocationMethod] = useState<'gps' | 'manual'>('gps');
  const [gpsStatus, setGpsStatus] = useState<'idle' | 'fetching' | 'success' | 'failed'>('idle');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Auto-fetch GPS location on load if selected
  useEffect(() => {
    if (locationMethod === 'gps') {
      fetchGPSLocation();
    }
  }, [locationMethod]);

  const fetchGPSLocation = () => {
    setGpsStatus('fetching');
    if (!navigator.geolocation) {
      setGpsStatus('failed');
      setLocationMethod('manual');
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLatitude(position.coords.latitude);
        setLongitude(position.coords.longitude);
        setGpsStatus('success');
      },
      (err) => {
        console.error(err);
        setGpsStatus('failed');
        setLocationMethod('manual');
      },
      { enableHighAccuracy: true, timeout: 5000, maximumAge: 0 }
    );
  };

  const handlePresetLocation = (city: 'bangalore' | 'mumbai' | 'rural') => {
    setLocationMethod('manual');
    if (city === 'bangalore') {
      setAddress('Bangalore Town Hall, Karnataka');
      setLatitude(12.9716);
      setLongitude(77.5946);
    } else if (city === 'mumbai') {
      setAddress('Gateway of India, Mumbai');
      setLatitude(19.0760);
      setLongitude(72.8777);
    } else {
      setAddress('Remote Rural Village, KA');
      setLatitude(15.3173);
      setLongitude(75.7139);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);

    const latVal = latitude;
    const lngVal = longitude;

    if (!symptom.trim()) {
      setError('Please describe your symptom or illness.');
      return;
    }

    if (latVal === null || lngVal === null) {
      setError('Please provide a location (either via GPS or manual address).');
      return;
    }

    setLoading(true);
    setFormSubmitted(true);

    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${backendUrl}/api/v1/intake`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symptom,
          lat: latVal,
          lng: lngVal,
          location_name: locationMethod === 'gps' ? 'GPS Coordinates' : address,
        }),
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const data = await response.json();
      setResult(data);
    } catch (err: any) {
      setError('Failed to submit intake. Please make sure the backend is running.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface text-text-primary flex flex-col font-sans selection:bg-brand-primary/20">
      {/* Decorative top gradient */}
      <div className="absolute top-0 left-0 right-0 h-[500px] bg-gradient-to-b from-emerald-950/20 via-transparent to-transparent pointer-events-none" />

      {/* Header */}
      <header className="relative w-full max-w-6xl mx-auto px-6 py-6 flex justify-between items-center z-10">
        <div className="flex items-center gap-2">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <svg className="w-5 h-5 text-slate-950 font-bold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-emerald-400 to-teal-300 bg-clip-text text-transparent">
              PulseDesk
            </h1>
            <p className="text-[10px] text-text-muted dark:text-slate-400 uppercase tracking-widest -mt-0.5">Emergency Dispatch</p>
          </div>
        </div>
        <div className="text-xs bg-surface-alt dark:bg-slate-900 border border-glass-border dark:border-slate-800 rounded-full px-3 py-1 text-text-muted dark:text-slate-400">
          Public Portal • No Login Required
        </div>
      </header>

      {/* Main Content */}
      <main className={`relative flex-1 w-full mx-auto px-6 py-8 z-10 transition duration-700 ease-in-out ${formSubmitted
        ? 'max-w-6xl grid grid-cols-1 md:grid-cols-12 gap-8 items-start'
        : 'max-w-full md:max-w-2xl flex flex-col items-center'
        }`}>

        {/* Form Column */}
        <section className={`bg-glass-bg backdrop-blur-md border border-glass-border rounded-3xl p-6 md:p-8 shadow-glass-dark z-20 transition duration-700 ${formSubmitted ? 'md:col-span-7 w-full' : 'w-full'
          }`}>
          <h2 className="text-2xl font-bold tracking-tight mb-2 text-text-primary">Patient Intake & Triage</h2>
          <p className="text-text-muted text-sm mb-6">
            Describe your symptoms. If classified as an emergency, PulseDesk will dispatch the nearest ambulance and find an available hospital bed.
          </p>

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Symptom Input */}
            <div className="space-y-2">
              <label htmlFor="symptom-input" className="block text-xs font-semibold uppercase tracking-wider text-text-muted dark:text-slate-400">
                1. Describe Symptoms / Illness
              </label>
              <textarea
                id="symptom-input"
                rows={4}
                className="w-full bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-2xl px-4 py-3 text-text-primary dark:text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
                placeholder="Describe what you are feeling (e.g. 'Severe chest pain radiating to left arm', 'High fever and mild cough'..."
                value={symptom}
                onChange={(e) => setSymptom(e.target.value)}
              />
              <div className="flex gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={() => setSymptom('Severe chest pain, breathlessness, and sweating')}
                  className="text-xs bg-surface-alt dark:bg-slate-950 hover:bg-surface dark:bg-slate-800 border border-glass-border dark:border-slate-800 rounded-lg px-2.5 py-2.5 min-h-[44px] md:min-h-0 flex items-center justify-center text-text-muted dark:text-slate-400 hover:text-white transition"
                >
                  ⚡ Try Emergency Symptom
                </button>
                <button
                  type="button"
                  onClick={() => setSymptom('Mild headache and sore throat')}
                  className="text-xs bg-surface-alt dark:bg-slate-950 hover:bg-surface dark:bg-slate-800 border border-glass-border dark:border-slate-800 rounded-lg px-2.5 py-2.5 min-h-[44px] md:min-h-0 flex items-center justify-center text-text-muted dark:text-slate-400 hover:text-white transition"
                >
                  🍃 Try Non-Emergency Symptom
                </button>
              </div>
            </div>

            {/* Location Section */}
            <div className="space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-wider text-text-muted dark:text-slate-400">
                2. Your Location
              </label>

              <div className="grid grid-cols-2 gap-2 bg-surface-alt dark:bg-slate-950 p-1 border border-glass-border dark:border-slate-800 rounded-xl">
                <button
                  type="button"
                  className={`py-3 md:py-2 text-xs font-medium rounded-lg transition min-h-[44px] md:min-h-0 flex items-center justify-center ${locationMethod === 'gps' ? 'bg-emerald-500 text-slate-950 font-bold' : 'text-text-muted dark:text-slate-400 hover:text-white'}`}
                  onClick={() => setLocationMethod('gps')}
                >
                  Browser GPS
                </button>
                <button
                  type="button"
                  className={`py-3 md:py-2 text-xs font-medium rounded-lg transition min-h-[44px] md:min-h-0 flex items-center justify-center ${locationMethod === 'manual' ? 'bg-emerald-500 text-slate-950 font-bold' : 'text-text-muted dark:text-slate-400 hover:text-white'}`}
                  onClick={() => setLocationMethod('manual')}
                >
                  Manual Address / Coordinates
                </button>
              </div>

              <AnimatePresence mode="wait">
                {locationMethod === 'gps' && (
                  <motion.div
                    key="gps"
                    initial={{ opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={{ duration: 0.2 }}
                    className="bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-2xl p-4 flex items-center justify-between"
                  >
                    <div>
                      <div className="text-xs font-medium text-text-muted dark:text-slate-400">GPS Coordinates Status</div>
                      <div className="text-sm font-semibold mt-1">
                        {gpsStatus === 'idle' && 'Waiting to fetch...'}
                        {gpsStatus === 'fetching' && 'Retrieving current position...'}
                        {gpsStatus === 'success' && `Latitude: ${latitude?.toFixed(4)}, Longitude: ${longitude?.toFixed(4)}`}
                        {gpsStatus === 'failed' && 'GPS access failed/denied.'}
                      </div>
                    </div>
                    {gpsStatus === 'failed' ? (
                      <span className="text-xs text-rose-400 font-medium">Please switch to manual</span>
                    ) : (
                      <button
                        type="button"
                        onClick={fetchGPSLocation}
                        className="text-xs bg-surface-alt dark:bg-slate-900 border border-glass-border dark:border-slate-800 hover:bg-surface dark:bg-slate-800 rounded-lg px-3 py-1.5 transition text-text-primary dark:text-white"
                      >
                        Retry GPS
                      </button>
                    )}
                  </motion.div>
                )}

                {locationMethod === 'manual' && (
                  <motion.div
                    key="manual"
                    initial={{ opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={{ duration: 0.2 }}
                    className="space-y-3 bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-2xl p-4"
                  >
                    <div className="text-xs text-text-muted dark:text-slate-400 mb-1">
                      Select a preset testing location or enter custom coordinates below.
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => handlePresetLocation('bangalore')}
                        className="text-[11px] bg-surface-alt dark:bg-slate-900 hover:bg-surface dark:bg-slate-800 border border-glass-border dark:border-slate-800 rounded-lg py-3 sm:py-1.5 text-center transition text-text-primary dark:text-white min-h-[44px] sm:min-h-0 flex items-center justify-center"
                      >
                        Bangalore (Near)
                      </button>
                      <button
                        type="button"
                        onClick={() => handlePresetLocation('mumbai')}
                        className="text-[11px] bg-surface-alt dark:bg-slate-900 hover:bg-surface dark:bg-slate-800 border border-glass-border dark:border-slate-800 rounded-lg py-3 sm:py-1.5 text-center transition text-text-primary dark:text-white min-h-[44px] sm:min-h-0 flex items-center justify-center"
                      >
                        Mumbai (Far)
                      </button>
                      <button
                        type="button"
                        onClick={() => handlePresetLocation('rural')}
                        className="text-[11px] bg-surface-alt dark:bg-slate-900 hover:bg-surface dark:bg-slate-800 border border-glass-border dark:border-slate-800 rounded-lg py-3 sm:py-1.5 text-center transition text-text-primary dark:text-white min-h-[44px] sm:min-h-0 flex items-center justify-center"
                      >
                        Remote Rural
                      </button>
                    </div>

                    <div className="space-y-2">
                      <label htmlFor="address-input" className="block text-[10px] uppercase tracking-wider text-slate-500">Typed Address / Location Name</label>
                      <input
                        id="address-input"
                        type="text"
                        className="w-full bg-surface-alt dark:bg-slate-900 border border-glass-border dark:border-slate-800 rounded-xl px-3 py-3 md:py-2 text-base md:text-sm min-h-[44px] md:min-h-0 text-text-primary dark:text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500"
                        placeholder="Enter city or area name..."
                        value={address}
                        onChange={(e) => setAddress(e.target.value)}
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label htmlFor="latitude-input" className="block text-[10px] uppercase tracking-wider text-slate-500">Latitude</label>
                        <input
                          id="latitude-input"
                          type="number"
                          step="any"
                          className="w-full bg-surface-alt dark:bg-slate-900 border border-glass-border dark:border-slate-800 rounded-xl px-3 py-3 md:py-2 text-base md:text-sm min-h-[44px] md:min-h-0 text-text-primary dark:text-slate-100 focus:outline-none"
                          value={latitude || ''}
                          onChange={(e) => setLatitude(e.target.value ? parseFloat(e.target.value) : null)}
                        />
                      </div>
                      <div>
                        <label htmlFor="longitude-input" className="block text-[10px] uppercase tracking-wider text-slate-500">Longitude</label>
                        <input
                          id="longitude-input"
                          type="number"
                          step="any"
                          className="w-full bg-surface-alt dark:bg-slate-900 border border-glass-border dark:border-slate-800 rounded-xl px-3 py-3 md:py-2 text-base md:text-sm min-h-[44px] md:min-h-0 text-text-primary dark:text-slate-100 focus:outline-none"
                          value={longitude || ''}
                          onChange={(e) => setLongitude(e.target.value ? parseFloat(e.target.value) : null)}
                        />
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {error && (
              <div id="error-message" className="bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 rounded-xl px-4 py-3 text-sm text-rose-800 dark:text-rose-300">
                {error}
              </div>
            )}

            <button
              id="submit-button"
              type="submit"
              disabled={loading}
              className={`w-full py-4 rounded-2xl font-bold text-sm tracking-wide uppercase transition duration-200 ${loading
                ? 'bg-surface dark:bg-slate-800 text-text-muted dark:text-slate-400 cursor-not-allowed'
                : 'bg-gradient-to-r from-emerald-500 to-teal-400 hover:from-emerald-400 hover:to-teal-300 text-slate-950 shadow-lg shadow-emerald-500/10'
                }`}
            >
              {loading ? 'Processing Triage...' : 'Submit Emergency Intake'}
            </button>
          </form>
        </section>

        {/* Results Column Container */}
        <div className={`transition duration-700 transform ${formSubmitted ? 'md:col-span-5 relative min-h-[400px] w-full opacity-100 translate-x-0' : 'hidden opacity-0 translate-x-8'}`}>

          {/* Actual Results Card */}
          <section className="absolute inset-0 bg-glass-bg backdrop-blur-md border border-glass-border shadow-glass-dark rounded-3xl p-6 flex flex-col justify-between">
            <div className="flex-1 flex flex-col justify-center items-center text-center p-4">
              {!result && !loading && formSubmitted && (
                <div id="empty-state">
                  <div className="w-16 h-16 rounded-full bg-surface-alt dark:bg-slate-900 border border-glass-border dark:border-slate-800 flex items-center justify-center mx-auto mb-4 text-slate-500">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold text-text-primary dark:text-slate-200">Waiting for Results</h3>
                  <p className="text-slate-500 text-xs mt-1 max-w-[240px]">
                    Real-time updates and dispatcher status will display here once processed.
                  </p>
                </div>
              )}

              {loading && (
                <div id="loading-state">
                  <div className="relative w-12 h-12 mb-4 mx-auto">
                    <div className="absolute inset-0 rounded-full border-4 border-glass-border dark:border-slate-800" />
                    <div className="absolute inset-0 rounded-full border-4 border-emerald-500 border-t-transparent animate-spin" />
                  </div>
                  <h3 className="text-sm font-medium text-text-muted dark:text-slate-300">Analyzing triage severity...</h3>
                  <p className="text-[11px] text-slate-500 mt-1">Estimating distance to available facilities</p>
                </div>
              )}

              {result && (
                <div id="result-container" className="w-full text-left space-y-6">
                  <div className="text-center pb-2 border-b border-glass-border dark:border-slate-800">
                    <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${result.severity === 'emergency' ? 'bg-rose-50 dark:bg-rose-950 text-rose-800 dark:text-rose-300 border border-rose-200 dark:border-rose-900/50' : 'bg-blue-50 dark:bg-blue-950 text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-900/50'
                      }`}>
                      Triage: {result.severity}
                    </span>
                  </div>

                  {result.status === 'dispatched' && (
                    <div id="dispatch-success-card" className="space-y-4">
                      <div className="bg-emerald-950/20 border border-emerald-900/40 rounded-2xl p-4 flex items-start gap-3">
                        <div className="mt-0.5 h-5 w-5 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-400">
                          ✓
                        </div>
                        <div>
                          <h4 className="text-sm font-bold text-emerald-400">Ambulance Dispatched</h4>
                          <p className="text-text-muted dark:text-slate-400 text-xs mt-0.5">
                            An ambulance from the nearest capable facility is currently route.
                          </p>
                        </div>
                      </div>

                      <div className="bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-2xl p-5 space-y-4">
                        <div>
                          <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest">Matched Facility</div>
                          <div id="facility-name-display" className="text-base font-bold text-text-primary dark:text-white mt-0.5">{result.facility_name}</div>
                        </div>
                        <div className="grid grid-cols-2 gap-4 pt-2 border-t border-glass-border dark:border-slate-900">
                          <div>
                            <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest">Estimated ETA</div>
                            <div id="eta-display" className="text-lg font-extrabold text-emerald-400 mt-0.5">{result.eta} mins</div>
                          </div>
                          <div>
                            <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest">Live Status</div>
                            <div className="text-xs font-bold text-text-primary dark:text-white mt-1.5 flex items-center gap-1.5">
                              <span className="h-2 w-2 rounded-full bg-amber-500 animate-ping" />
                              Pending Acknowledgment
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {result.status === 'escalated' && (
                    <div id="escalated-card" className="space-y-4">
                      <div className="bg-amber-950/30 border border-amber-900/50 rounded-2xl p-4 flex items-start gap-3">
                        <div className="mt-0.5 h-5 w-5 rounded-full bg-amber-500/20 flex items-center justify-center text-amber-400 font-bold">
                          !
                        </div>
                        <div>
                          <h4 className="text-sm font-bold text-amber-400">Surge Escalation</h4>
                          <p className="text-text-muted dark:text-slate-400 text-xs mt-0.5">
                            No nearby facility within a 50 km radius has available bed capacity.
                          </p>
                        </div>
                      </div>

                      <div className="bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-2xl p-5 space-y-4">
                        <h4 className="text-sm font-bold text-text-primary dark:text-white">Escalated to District-Admin</h4>
                        <p className="text-text-muted dark:text-slate-400 text-xs">
                          Triage alerts have been pushed directly to the district administration dashboard for manual hospital bed matching and ambulance rerouting.
                        </p>
                        <div className="pt-2 border-t border-glass-border dark:border-slate-900 flex justify-between items-center text-xs">
                          <span className="text-slate-500">District Scope Code:</span>
                          <span id="district-code-display" className="font-mono font-bold text-amber-400 bg-amber-950/20 px-2 py-0.5 rounded border border-amber-900/40">
                            {result.district_code}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}

                  {result.status === 'triage' && (
                    <div id="triage-non-emergency-card" className="bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-2xl p-5 space-y-3">
                      <h4 className="text-sm font-bold text-text-primary dark:text-white">General Clinic Advice</h4>
                      <p className="text-text-muted dark:text-slate-400 text-xs leading-relaxed">
                        {result.message}
                      </p>
                      <p className="text-slate-500 text-[11px] leading-relaxed">
                        If your symptoms worsen or you start experiencing breathing difficulties, chest tightness, or severe bleeding, please call emergency services immediately or submit a new report.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="text-[10px] text-slate-600 text-center border-t border-glass-border dark:border-slate-900 pt-4 mt-4">
              Security Protected • Coordinates transmitted directly to local government servers
            </div>
          </section>
        </div>

      </main>

      {/* Footer */}
      <footer className="w-full text-center py-8 text-xs text-slate-600 border-t border-glass-border dark:border-slate-900 mt-12 z-10" suppressHydrationWarning>
        PulseDesk © {new Date().getFullYear()} • Made by Team CodeCraft
      </footer>
    </div>
  );
}
