'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function DashboardSwitcher() {
  const [isOpen, setIsOpen] = useState(false);
  const [role, setRole] = useState<'receptionist' | 'phc_incharge' | 'district_admin'>('receptionist');
  const [identifier, setIdentifier] = useState(''); // facility_id or district_code
  const [password, setPassword] = useState(''); // mock password verification
  const [error, setError] = useState<string | null>(null);
  
  const router = useRouter();
  const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const handleSwitch = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Simple password validator (e.g. admin123 or swasthya2026 or any non-empty)
    if (!password) {
      setError('Password is required');
      return;
    }

    if (password !== 'admin123' && password !== 'swasthya2026') {
      setError('Invalid credentials');
      return;
    }

    try {
      const payload: any = { role };
      if (role === 'district_admin') {
        payload.district_code = identifier || 'KA-BNG';
      } else {
        if (identifier) {
          payload.facility_id = identifier;
        } else {
          const facRes = await fetch(`${backendUrl}/api/v1/facilities`);
          const facList = await facRes.json();
          if (facList && facList.length > 0) {
            payload.facility_id = facList[0].id;
          } else {
            throw new Error("No facilities found in the database. Did you run the seed script?");
          }
        }
      }

      const response = await fetch(`${backendUrl}/api/v1/auth/mock-login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error('Authentication failed');
      }

      const data = await response.json();
      
      // Store tokens and identifiers appropriately based on the role structure
      if (role === 'district_admin') {
        localStorage.setItem('da_token', data.access_token);
        localStorage.setItem('da_district', data.claims.district_code);
        router.push('/district-admin');
      } else {
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('facility_id', data.claims.facility_id);
        if (role === 'phc_incharge') {
          router.push('/phc-incharge');
        } else {
          router.push('/receptionist');
        }
      }
      setIsOpen(false);
      
      // Navigate using window.location.href to guarantee state reload and hard redirect
      setTimeout(() => {
        if (role === 'district_admin') {
          window.location.href = '/district-admin';
        } else if (role === 'phc_incharge') {
          window.location.href = '/phc-incharge';
        } else {
          window.location.href = '/receptionist';
        }
      }, 100);

    } catch (err: any) {
      setError(err.message || 'Failed to authenticate and switch');
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50">
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-14 h-14 bg-gradient-to-r from-blue-600 to-indigo-600 text-text-primary dark:text-white rounded-full flex items-center justify-center shadow-lg hover:shadow-indigo-500/50 hover:scale-105 active:scale-95 transition-all duration-200 border border-indigo-400/20"
        title="Switch Dashboard"
        id="dashboard-switcher-trigger"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
        </svg>
      </button>

      {/* Modal / Popover */}
      {isOpen && (
        <div className="absolute bottom-16 right-0 w-80 bg-surface-alt dark:bg-slate-900 border border-glass-border dark:border-slate-800 rounded-3xl p-5 shadow-2xl text-text-primary dark:text-slate-200 backdrop-blur-md animate-in fade-in slide-in-from-bottom-5 duration-200">
          <div className="flex justify-between items-center mb-4 pb-2 border-b border-glass-border dark:border-slate-800">
            <h3 className="font-bold text-sm tracking-wide text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-400">
              Dashboard Gateway
            </h3>
            <button
              onClick={() => setIsOpen(false)}
              className="text-slate-500 hover:text-text-muted dark:text-slate-300 transition text-xs px-3 py-1.5 min-h-[44px] md:min-h-0 flex items-center justify-center"
            >
              Close
            </button>
          </div>

          <form onSubmit={handleSwitch} className="space-y-3">
            {/* Target Role Selector */}
            <div>
              <label className="text-[10px] text-text-muted dark:text-slate-400 uppercase tracking-widest font-semibold block mb-1">Target Role</label>
              <select
                value={role}
                onChange={(e: any) => setRole(e.target.value)}
                className="w-full bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-xl px-3 py-3 md:py-2 text-base md:text-xs min-h-[44px] md:min-h-0 focus:outline-none focus:border-indigo-500 text-text-primary dark:text-slate-200"
              >
                <option value="receptionist">Receptionist</option>
                <option value="phc_incharge">PHC In-charge</option>
                <option value="district_admin">District Admin</option>
              </select>
            </div>

            {/* Scope Identifier */}
            <div>
              <label className="text-[10px] text-text-muted dark:text-slate-400 uppercase tracking-widest font-semibold block mb-1">
                {role === 'district_admin' ? 'District Code' : 'Facility ID'}
              </label>
              <input
                type="text"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder={role === 'district_admin' ? 'E.g. KA-BNG' : 'E.g. uuid-string-here'}
                className="w-full bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-xl px-3 py-3 md:py-2 text-base md:text-xs min-h-[44px] md:min-h-0 focus:outline-none focus:border-indigo-500 text-text-primary dark:text-slate-200"
              />
            </div>

            {/* Password */}
            <div>
              <label className="text-[10px] text-text-muted dark:text-slate-400 uppercase tracking-widest font-semibold block mb-1">Secret Key / Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="E.g. admin123"
                className="w-full bg-surface-alt dark:bg-slate-950 border border-glass-border dark:border-slate-800 rounded-xl px-3 py-3 md:py-2 text-base md:text-xs min-h-[44px] md:min-h-0 focus:outline-none focus:border-indigo-500 text-text-primary dark:text-slate-200"
              />
            </div>

            {error && (
              <p className="text-[10px] text-rose-400 font-semibold bg-rose-950/20 border border-rose-900/30 rounded-lg p-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-slate-50 font-bold py-3 md:py-2 min-h-[44px] md:min-h-0 rounded-xl text-xs transition duration-150 flex items-center justify-center"
            >
              Authenticate & Switch
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
