'use client';

import React, { useState, useEffect, useRef } from 'react';
import { db } from '@/lib/db';

export default function ReceptionistDashboard() {
  const [token, setToken] = useState<string | null>(null);
  const [facilityId, setFacilityId] = useState<string | null>(null);
  const [facilities, setFacilities] = useState<any[]>([]);
  const [selectedFacility, setSelectedFacility] = useState<string>('');
  
  // Dashboard data
  const [dashboardData, setDashboardData] = useState<any | null>(null);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Walk-in form states
  const [patientName, setPatientName] = useState('');
  const [patientAge, setPatientAge] = useState('');
  const [patientGender, setPatientGender] = useState('Male');
  const [patientSymptoms, setPatientSymptoms] = useState('');
  const [registering, setRegistering] = useState(false);
  const [registerMessage, setRegisterMessage] = useState<string | null>(null);
  
  // Voice Log states
  const [voiceText, setVoiceText] = useState('OPD footfall is 120 patients today');
  const [transcribing, setTranscribing] = useState(false);
  const [transcribeResult, setTranscribeResult] = useState<any | null>(null);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  
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

    const fetchData = async () => {
      try {
        const response = await fetch(`${backendUrl}/api/v1/receptionist/data/${facilityId}`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (!response.ok) {
          if (response.status === 401 || response.status === 403) {
            handleLogout();
            throw new Error('Session expired or unauthorized');
          }
          throw new Error('Failed to fetch dashboard data');
        }
        const data = await response.json();
        setDashboardData(data);
        setError(null);
      } catch (err: any) {
        setError(err.message);
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
          role: 'receptionist',
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
  };

  const handleWalkInSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!patientName.trim() || !patientSymptoms.trim() || !patientAge) {
      setRegisterMessage('Please fill all walk-in details.');
      return;
    }
    setRegistering(true);
    setRegisterMessage(null);
    try {
      const response = await fetch(`${backendUrl}/api/v1/receptionist/walk-in/${facilityId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          patient_name: patientName,
          age: parseInt(patientAge),
          gender: patientGender,
          symptoms: patientSymptoms,
        }),
      });

      if (!response.ok) {
        throw new Error('Registration failed');
      }

      const data = await response.json();
      setRegisterMessage(`Walk-in registered successfully. Severity: ${data.severity}`);
      setPatientName('');
      setPatientAge('');
      setPatientSymptoms('');
    } catch (err: any) {
      // Fallback to offline storage if network fails
      if (err.name === 'TypeError' || err.message === 'Failed to fetch') {
        try {
          await db.walkIns.add({
            patient_name: patientName,
            age: parseInt(patientAge),
            gender: patientGender,
            symptoms: patientSymptoms,
            facility_id: facilityId!,
            synced: 0
          });
          setRegisterMessage('Saved offline. Will sync when online.');
          setPatientName('');
          setPatientAge('');
          setPatientSymptoms('');
        } catch (dbErr) {
          setRegisterMessage(`Error: Failed to save offline data.`);
        }
      } else {
        setRegisterMessage(`Error: ${err.message}`);
      }
    } finally {
      setRegistering(false);
    }
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
        ).filter((d: any) => d.status !== 'arrived'); // Remove if marked arrived
        setDashboardData({ ...dashboardData, active_dispatches: updatedDispatches });
      }
    } catch (err: any) {
      alert(`Error updating dispatch: ${err.message}`);
    }
  };

  // Submits a mock audio file with custom mock_text
  const handleVoiceTranscribeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!voiceText.trim()) return;

    setTranscribing(true);
    setTranscribeResult(null);
    setVoiceError(null);

    try {
      // Create a dummy WAV file (44 byte header + silence)
      const buffer = new ArrayBuffer(44);
      const view = new DataView(buffer);
      // Construct a valid standard WAV header so backend validation doesn't crash on format checks
      /* RIFF identifier */
      view.setUint32(0, 0x52494646, false); // "RIFF"
      /* file length */
      view.setUint32(4, 36, true);
      /* RIFF type */
      view.setUint32(8, 0x57415645, false); // "WAVE"
      /* format chunk identifier */
      view.setUint32(12, 0x666d7420, false); // "fmt "
      /* format chunk length */
      view.setUint32(16, 16, true);
      /* sample format (raw) */
      view.setUint16(20, 1, true);
      /* channel count */
      view.setUint16(22, 1, true);
      /* sample rate */
      view.setUint32(24, 16000, true);
      /* byte rate (sample rate * block align) */
      view.setUint32(28, 32000, true);
      /* block align (channel count * bytes per sample) */
      view.setUint16(32, 2, true);
      /* bits per sample */
      view.setUint16(34, 16, true);
      /* data chunk identifier */
      view.setUint32(36, 0x64617461, false); // "data"
      /* data chunk length */
      view.setUint32(40, 0, true);

      const audioBlob = new Blob([buffer], { type: 'audio/wav' });
      const formData = new FormData();
      formData.append('file', audioBlob, 'mock_voice.wav');
      formData.append('mock_text', voiceText);

      const response = await fetch(`${backendUrl}/api/v1/voice/transcribe`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Transcription round-trip failed');
      }

      const data = await response.json();
      setTranscribeResult(data);
      
      // If the intent resulted in a DB update, we'll see it reflected soon in our polled data.
    } catch (err: any) {
      setVoiceError(err.message);
    } finally {
      setTranscribing(false);
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
            <p className="text-xs text-text-muted mt-1 uppercase tracking-widest">Receptionist Login</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-6">
            <div className="space-y-2">
              <label htmlFor="facility-select" className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                Select Your Facility
              </label>
              <select
                id="facility-select"
                className="w-full bg-slate-950 border border-slate-800 rounded-2xl px-4 py-3 text-slate-100 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
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
              Sign In as Receptionist
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
            <p className="text-[9px] text-text-muted uppercase tracking-widest -mt-0.5">Receptionist Console</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {dashboardData && (
            <div id="logged-in-facility-badge" className="text-xs bg-slate-900 border border-slate-800 rounded-full px-3 py-1.5 text-slate-300 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              {dashboardData.facility_name}
            </div>
          )}
          <button
            id="logout-button"
            onClick={handleLogout}
            className="text-xs bg-rose-950/20 hover:bg-rose-950/40 border border-rose-900/40 text-rose-300 rounded-xl px-3.5 py-1.5 transition"
          >
            Sign Out
          </button>
        </div>
      </header>

      {error && (
        <div className="bg-rose-950/30 border-b border-rose-900/50 px-6 py-3 text-sm text-rose-300 text-center">
          ⚠️ Connection Error: {error}
        </div>
      )}

      <main className="flex-1 w-full max-w-7xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start z-10">
        
        {/* LEFT COLUMN: 60% Width for Walk-ins & Queue */}
        <div className="lg:col-span-7 space-y-8">
          
          {/* Walk-in Form & Queue Panel */}
          <section className="bg-glass-bg backdrop-blur-md border border-glass-border rounded-3xl p-6 shadow-glass-dark space-y-6">
            <div>
              <h2 className="text-xl font-bold text-text-primary">Walk-in Patient Registration</h2>
              <p className="text-text-muted text-xs mt-1">Register walk-in patients directly to the local facility queue.</p>
            </div>

            <form onSubmit={handleWalkInSubmit} className="grid grid-cols-1 md:grid-cols-12 gap-4">
              <div className="md:col-span-5 space-y-1">
                <label htmlFor="patient-name-input" className="block text-[10px] uppercase font-bold tracking-wider text-slate-400">Patient Name</label>
                <input
                  id="patient-name-input"
                  type="text"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-emerald-500"
                  placeholder="Enter full name"
                  value={patientName}
                  onChange={(e) => setPatientName(e.target.value)}
                />
              </div>

              <div className="md:col-span-2 space-y-1">
                <label htmlFor="patient-age-input" className="block text-[10px] uppercase font-bold tracking-wider text-slate-400">Age</label>
                <input
                  id="patient-age-input"
                  type="number"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-emerald-500"
                  placeholder="Years"
                  value={patientAge}
                  onChange={(e) => setPatientAge(e.target.value)}
                />
              </div>

              <div className="md:col-span-2 space-y-1">
                <label htmlFor="patient-gender-select" className="block text-[10px] uppercase font-bold tracking-wider text-slate-400">Gender</label>
                <select
                  id="patient-gender-select"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-emerald-500"
                  value={patientGender}
                  onChange={(e) => setPatientGender(e.target.value)}
                >
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              <div className="md:col-span-3 flex items-end">
                <button
                  id="register-patient-button"
                  type="submit"
                  disabled={registering}
                  className="w-full py-2.5 rounded-xl font-semibold text-xs uppercase tracking-wide bg-gradient-to-r from-emerald-500 to-teal-400 text-slate-950 hover:from-emerald-400 hover:to-teal-300 disabled:bg-slate-800 disabled:text-slate-500 transition duration-200"
                >
                  {registering ? 'Registering...' : 'Register'}
                </button>
              </div>

              <div className="md:col-span-12 space-y-1">
                <label htmlFor="patient-symptoms-input" className="block text-[10px] uppercase font-bold tracking-wider text-slate-400">Symptoms & Clinical Details</label>
                <textarea
                  id="patient-symptoms-input"
                  rows={2}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-emerald-500"
                  placeholder="Describe patient condition/symptoms..."
                  value={patientSymptoms}
                  onChange={(e) => setPatientSymptoms(e.target.value)}
                />
              </div>
            </form>

            {registerMessage && (
              <div id="registration-status-message" className={`p-3 rounded-xl text-xs border ${
                registerMessage.includes('Error') ? 'bg-rose-950/20 border-rose-900/40 text-rose-300' : 'bg-emerald-950/20 border-emerald-900/40 text-emerald-300'
              }`}>
                {registerMessage}
              </div>
            )}

            {/* Walk-in Queue Table */}
            <div className="space-y-3 pt-4 border-t border-slate-900">
              <h3 className="text-sm font-bold text-slate-200">Today's Walk-in Queue</h3>
              
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-500">
                      <th className="py-2.5">Time</th>
                      <th className="py-2.5">Patient / Symptoms</th>
                      <th className="py-2.5 text-right">Triage Severity</th>
                    </tr>
                  </thead>
                  <tbody id="walk-in-queue-body">
                    {dashboardData?.walk_ins && dashboardData.walk_ins.length > 0 ? (
                      dashboardData.walk_ins.map((w: any) => (
                        <tr key={w.id} className="border-b border-slate-900/50 hover:bg-slate-900/10">
                          <td className="py-2.5 text-slate-400 font-mono">
                            {new Date(w.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </td>
                          <td className="py-2.5 pr-4">
                            <span className="font-semibold text-slate-200">{w.symptoms}</span>
                          </td>
                          <td className="py-2.5 text-right">
                            <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                              w.severity === 'emergency' ? 'bg-rose-950 text-rose-300 border border-rose-900/30' : 'bg-slate-950 text-slate-400 border border-slate-800'
                            }`}>
                              {w.severity}
                            </span>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={3} className="py-6 text-center text-slate-500 italic">
                          No walk-in patients registered today.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {/* Voice Log Entry Panel */}
          <section className="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-6 shadow-xl space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  Voice-Log Terminal 
                  {transcribing && <span className="flex h-2.5 w-2.5 relative"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span><span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500"></span></span>}
                </h2>
                <p className="text-slate-400 text-xs mt-1">Speak inventory updates, footfall count, or attendance logs.</p>
              </div>
            </div>

            {/* Simulated Canvas Waveform */}
            <div className="w-full h-16 bg-slate-950 border border-slate-800/50 rounded-xl overflow-hidden flex items-center justify-center gap-1 opacity-80">
              {Array.from({ length: 30 }).map((_, i) => (
                <div key={i} className={`w-1 bg-emerald-500/40 rounded-full ${transcribing ? 'animate-pulse-critical bg-rose-500' : ''}`} style={{ height: transcribing ? `${Math.max(20, Math.random() * 100)}%` : '10%' }} />
              ))}
            </div>

            <form onSubmit={handleVoiceTranscribeSubmit} className="space-y-4">
              <div className="space-y-2">
                <label htmlFor="voice-log-text-input" className="block text-[10px] uppercase font-bold tracking-wider text-slate-400">
                  Simulate Speech / Audio Transcription (Local Mock)
                </label>
                <div className="flex gap-3">
                  <input
                    id="voice-log-text-input"
                    type="text"
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-emerald-500"
                    placeholder="E.g., OPD footfall is 120 patients today"
                    value={voiceText}
                    onChange={(e) => setVoiceText(e.target.value)}
                  />
                  
                  <button
                    id="voice-transcribe-submit-button"
                    type="submit"
                    disabled={transcribing}
                    className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 rounded-xl px-5 font-semibold text-xs uppercase tracking-wider disabled:bg-slate-800 disabled:text-slate-500 transition"
                  >
                    {transcribing ? 'Processing...' : 'Voice Log'}
                  </button>
                </div>
              </div>

              {/* Sample phrases for quick testing */}
              <div className="flex flex-wrap gap-2">
                <span className="text-[10px] text-slate-500 uppercase tracking-wider flex items-center">Presets:</span>
                <button
                  type="button"
                  onClick={() => setVoiceText('OPD footfall is 120 patients today')}
                  className="text-[10px] bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-lg px-2.5 py-1 text-slate-400 transition"
                >
                  Footfall: 120
                </button>
                <button
                  type="button"
                  onClick={() => setVoiceText('Paracetamol stock khatam ho gaya hai')}
                  className="text-[10px] bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-lg px-2.5 py-1 text-slate-400 transition"
                >
                  Stock: Paracetamol (Empty)
                </button>
                <button
                  type="button"
                  onClick={() => setVoiceText('Amoxicillin stock is 45 packages')}
                  className="text-[10px] bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-lg px-2.5 py-1 text-slate-400 transition"
                >
                  Stock: Amoxicillin 45
                </button>
              </div>
            </form>

            {voiceError && (
              <div id="voice-error-display" className="bg-rose-950/20 border border-rose-900/40 rounded-xl p-3 text-xs text-rose-300">
                Error: {voiceError}
              </div>
            )}

            {transcribeResult && (
              <div id="transcription-result-card" className="bg-slate-950 border border-slate-800 rounded-2xl p-5 space-y-4">
                <h4 className="text-xs font-bold text-white uppercase tracking-wider">Transcription Round-trip Details</h4>
                
                <div className="grid grid-cols-2 gap-4 text-xs">
                  <div className="col-span-2">
                    <span className="text-slate-500">Transcribed Text:</span>
                    <p id="transcribed-text-display" className="font-semibold text-slate-200 mt-0.5">{transcribeResult.transcribed_text}</p>
                  </div>
                  <div>
                    <span className="text-slate-500">Detected Intent:</span>
                    <p id="detected-intent-display" className="font-mono font-bold text-emerald-400 mt-0.5">{transcribeResult.intent}</p>
                  </div>
                  <div>
                    <span className="text-slate-500">Confidence Score:</span>
                    <p className="font-mono text-slate-400 mt-0.5">{transcribeResult.confidence_score.toFixed(2)}</p>
                  </div>
                  {transcribeResult.extracted_entity && (
                    <div>
                      <span className="text-slate-500">Extracted Entity:</span>
                      <p id="extracted-entity-display" className="font-semibold text-slate-200 mt-0.5">{transcribeResult.extracted_entity}</p>
                    </div>
                  )}
                  {transcribeResult.extracted_value !== null && (
                    <div>
                      <span className="text-slate-500">Extracted Value:</span>
                      <p id="extracted-value-display" className="font-mono font-bold text-emerald-400 mt-0.5">{String(transcribeResult.extracted_value)}</p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>

        </div>

        {/* RIGHT COLUMN: 40% Width for Voice Log & Bed Panel */}
        <div className="lg:col-span-5 space-y-8">
          
          {/* Bed Availability Panel */}
          <section className="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-6 shadow-xl space-y-4">
            <h2 className="text-base font-bold text-white">Bed Availability Panel</h2>
            <p className="text-slate-400 text-xs -mt-2">Read-only facility capacity index</p>
            
            {dashboardData ? (
              <div className="bg-slate-950 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div>
                  <div className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold">Facility Name</div>
                  <div className="text-sm font-bold text-white mt-0.5">{dashboardData.facility_name}</div>
                </div>
                
                <div className="grid grid-cols-2 gap-4 pt-2 border-t border-slate-900">
                  <div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold">Available Beds</div>
                    <div id="available-beds-display" className="text-xl font-extrabold text-emerald-400 mt-0.5">
                      {dashboardData.available_beds}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold">Sanctioned Beds</div>
                    <div className="text-lg font-bold text-slate-300 mt-0.5">
                      {dashboardData.sanctioned_beds}
                    </div>
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-900 flex justify-between items-center text-xs">
                  <span className="text-slate-500">Facility Type:</span>
                  <span className="font-bold text-white bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
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
        </div>

        {/* Live Dispatch Alerts Feed */}
        <div className="lg:col-span-12 space-y-8">
          <section className="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-6 shadow-xl space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-base font-bold text-white">Live Dispatch Alerts</h2>
              <span className="inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </div>
            <p className="text-slate-400 text-xs -mt-2">Incoming emergency transport alerts scoped to your facility.</p>

            <div id="dispatch-alerts-container" className="space-y-4 max-h-[400px] overflow-y-auto pr-1 grid grid-cols-1 md:grid-cols-2 gap-4">
              {dashboardData?.active_dispatches && dashboardData.active_dispatches.length > 0 ? (
                dashboardData.active_dispatches.map((d: any) => (
                  <div key={d.id} className="bg-slate-950 border border-slate-800 hover:border-slate-700/80 rounded-2xl p-4 space-y-3 transition duration-150">
                    <div className="flex justify-between items-start">
                      <span className="inline-block px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-rose-950 text-rose-300 border border-rose-900/30">
                        Ambulance Alert
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {d.eta ? `${new Date(d.eta).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} ETA` : 'Pending'}
                      </span>
                    </div>

                    <p className="text-slate-200 text-xs leading-relaxed font-semibold">
                      {d.symptom}
                    </p>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-900 text-xs">
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
                <div className="col-span-1 md:col-span-2 text-slate-500 text-xs italic text-center py-8 bg-slate-950/20 border border-slate-900 rounded-2xl">
                  No active incoming dispatches.
                </div>
              )}
            </div>
          </section>
        </div>
      </main>
      
      <footer className="w-full text-center py-6 text-[10px] text-text-muted border-t border-glass-border mt-12 bg-surface">
        PulseDesk Receptionist Dashboard © {new Date().getFullYear()} • Dynamic Triage & Dispatch Sentry
      </footer>
    </div>
  );
}
