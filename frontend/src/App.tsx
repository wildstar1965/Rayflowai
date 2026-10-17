import React, { useState } from 'react';
import LandingPage from './pages/LandingPage';
import StudioPage from './pages/StudioPage';

export function App() {
  const [currentPage, setCurrentPage] = useState<'landing' | 'studio'>('landing');

  return (
    <div className="min-h-screen bg-white text-zinc-900 font-sans">
      {currentPage === 'landing' ? (
        <LandingPage onEnterStudio={() => setCurrentPage('studio')} />
      ) : (
        <StudioPage onBackToHome={() => setCurrentPage('landing')} />
      )}
    </div>
  );
}

export default App;
