'use client';

import React, { useEffect, useState } from 'react';

export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(true); // Default to dark since globals.css dark variables are for Tactical Dark Mode

  useEffect(() => {
    const isDarkMode = document.documentElement.classList.contains('dark') || 
      (localStorage.getItem('theme') === 'dark') || 
      (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches);
    
    // We will enforce the dark mode by default unless localstorage says light
    const enforceDark = localStorage.getItem('theme') === 'light' ? false : true;

    if (enforceDark) {
      setIsDark(true);
      document.documentElement.classList.add('dark');
    } else {
      setIsDark(false);
      document.documentElement.classList.remove('dark');
    }
  }, []);

  const toggleTheme = () => {
    if (isDark) {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
      setIsDark(false);
    } else {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
      setIsDark(true);
    }
  };

  return (
    <button
      onClick={toggleTheme}
      className="fixed bottom-6 left-6 z-50 w-14 h-14 bg-surface text-text-primary rounded-full flex items-center justify-center shadow-glass-dark hover:scale-105 active:scale-95 transition-all duration-200 border border-glass-border"
      title="Toggle Dark Mode"
    >
      {isDark ? (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-brand-warning" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          {/* Sun icon for dark mode (click to go to light) */}
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      ) : (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-slate-800" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          {/* Moon icon for light mode (click to go to dark) */}
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
        </svg>
      )}
    </button>
  );
}
