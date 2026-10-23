import React, { useState, useEffect } from 'react';
import { Menu, X, ArrowRight } from 'lucide-react';
import { Button } from './Button';

interface NavbarProps {
  onEnterStudio: () => void;
  activeSection?: string;
}

export const Navbar: React.FC<NavbarProps> = ({ onEnterStudio }) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMobileMenuOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Prevent background scroll when mobile menu is open
  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [mobileMenuOpen]);

  const navLinks = [
    { label: 'Home', href: '#/' },
    { label: 'Dashboard', href: '#/dashboard' },
    { label: 'AI Editor', href: '#/editor' },
    { label: 'Connections', href: '#/connections' },
  ];

  return (
    <header className="sticky top-0 z-40 w-full bg-studio-panel/95 backdrop-blur-sm border-b border-studio-border">
      <div className="max-w-6xl mx-auto px-5 h-14 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-accent inline-block" />
          <span className="font-semibold text-sm tracking-tight text-studio-text">
            Rayflow
          </span>
          <span className="text-[11px] font-medium px-1.5 py-0.5 rounded bg-studio-hover text-studio-muted border border-studio-border">
            AI Studio
          </span>
        </div>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-7">
          {navLinks.map(link => (
            <a
              key={link.label}
              href={link.href}
              className="text-xs font-medium text-studio-muted hover:text-studio-text transition-colors"
            >
              {link.label}
            </a>
          ))}
        </nav>

        {/* Desktop CTA */}
        <div className="hidden md:flex items-center gap-3">
          <Button variant="primary" size="sm" onClick={onEnterStudio}>
            <span>Open Studio</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Button>
        </div>

        {/* Mobile menu trigger */}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="md:hidden p-1.5 text-studio-muted hover:text-studio-text transition-colors"
          aria-label={mobileMenuOpen ? 'Close Menu' : 'Open Menu'}
          aria-expanded={mobileMenuOpen}
        >
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile Menu Overlay */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 top-14 bg-studio-panel z-50 flex flex-col p-6 space-y-6 md:hidden animate-in fade-in duration-150">
          <div className="flex flex-col space-y-4">
            {navLinks.map(link => (
              <a
                key={link.label}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className="text-base font-medium text-studio-text hover:text-studio-text py-2 border-b border-studio-line"
              >
                {link.label}
              </a>
            ))}
          </div>

          <div className="pt-4">
            <Button
              variant="primary"
              size="lg"
              className="w-full"
              onClick={() => {
                setMobileMenuOpen(false);
                onEnterStudio();
              }}
            >
              <span>Open Studio</span>
              <ArrowRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </header>
  );
};

export default Navbar;
