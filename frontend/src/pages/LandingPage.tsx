import React, { useState } from 'react';
import { SoftAurora } from '../components/ui/SoftAurora';
import { MaskedHeading } from '../components/ui/MaskedHeading';
import { SpecularButton } from '../components/ui/SpecularButton';
import { StaggeredMenu, StaggeredMenuItem } from '../components/ui/StaggeredMenu';
import { Stepper, Step } from '../components/ui/Stepper';
import {
  Sparkles,
  Mic,
  Music,
  Video,
  Layers,
  ArrowRight,
  Clock,
  Wand2,
  Sliders,
  CheckCircle2,
  Film,
  Play
} from 'lucide-react';

interface LandingPageProps {
  onEnterStudio: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onEnterStudio }) => {
  const [showGuidedModal, setShowGuidedModal] = useState(false);
  const [guidedStep, setGuidedStep] = useState(1);

  const menuItems: StaggeredMenuItem[] = [
    { label: 'Home', link: '#hero' },
    { label: 'Studio', link: '#studio', onClick: onEnterStudio },
    { label: 'How It Works', link: '#how-it-works' },
    { label: 'Ray Tribute', link: '#tribute' },
  ];

  const socialItems = [
    { label: 'Documentation', link: 'https://github.com' },
    { label: 'Satyajit Ray Archive', link: 'https://satyajitray.org' },
    { label: 'GitHub', link: 'https://github.com' },
  ];

  return (
    <div className="relative min-h-screen bg-[#08090D] text-[#F5F7FB] selection:bg-accent-blue selection:text-white overflow-hidden">
      {/* Top Staggered Menu Navigation */}
      <div className="absolute top-0 left-0 right-0 z-50">
        <StaggeredMenu
          position="right"
          items={menuItems}
          socialItems={socialItems}
          accentColor="#3B82F6"
          colors={['#11131A', '#181B24', '#3B82F6']}
        />
      </div>

      {/* Hero Section */}
      <section id="hero" className="relative min-h-[92vh] flex flex-col items-center justify-center px-6 pt-28 pb-16 text-center">
        {/* Soft Aurora subtle background */}
        <div className="absolute inset-0 pointer-events-none opacity-50 z-0">
          <SoftAurora
            speed={0.35}
            scale={1.3}
            brightness={0.85}
            color1="#3B82F6"
            color2="#8B5CF6"
            bandHeight={0.45}
            bandSpread={1.2}
            mouseInfluence={0.2}
          />
        </div>

        {/* Ambient top vignette */}
        <div className="absolute inset-0 bg-radial-gradient from-transparent via-[#08090D]/50 to-[#08090D] pointer-events-none z-0" />

        {/* Content */}
        <div className="relative z-10 max-w-4xl mx-auto flex flex-col items-center">
          {/* Eyebrow */}
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-surface-elevated/80 border border-white/10 backdrop-blur-md mb-6 shadow-lg shadow-black/40">
            <span className="w-2 h-2 rounded-full bg-accent-cyan animate-pulse" />
            <span className="text-xs font-mono font-medium tracking-widest uppercase text-accent-cyan">
              VOICE-DRIVEN CINEMATIC EDITING
            </span>
          </div>

          {/* MaskedHeading for cinematic typography */}
          <div className="w-full max-w-3xl my-2">
            <MaskedHeading
              text="Your vision. Your voice. Your film."
              tag="h1"
              weight={800}
              tracking={-0.03}
              textScale={0.11}
              reveal="rise"
              duration={1.2}
              spotlight
              src="https://images.unsplash.com/photo-1536440136628-849c177e76a1?auto=format&fit=crop&w=1200&q=80"
              outline
              outlineColor="rgba(255,255,255,0.15)"
              className="font-cinematic text-4xl sm:text-6xl md:text-7xl font-extrabold tracking-tight"
            />
          </div>

          {/* Supporting Text */}
          <p className="mt-6 text-base sm:text-lg md:text-xl text-text-secondary max-w-2xl font-light leading-relaxed">
            Turn photographs, music, and creative instructions into cinematic reels.
            Direct your edit naturally and let RayFlow handle rhythm, beats, and timeline motion.
          </p>

          {/* CTAs */}
          <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
            <SpecularButton
              size="lg"
              radius={24}
              tint="#3B82F6"
              tintOpacity={0.12}
              lineColor="#67E8F9"
              textColor="#FFFFFF"
              onClick={onEnterStudio}
              className="font-medium px-8 py-4 shadow-xl shadow-accent-blue/20"
            >
              <div className="flex items-center gap-2">
                <span>Start Creating</span>
                <ArrowRight className="w-4 h-4 text-accent-cyan" />
              </div>
            </SpecularButton>

            <button
              onClick={() => setShowGuidedModal(true)}
              className="px-6 py-3.5 rounded-3xl bg-surface/80 hover:bg-surface-hover border border-white/10 text-sm font-medium text-text-primary transition-all duration-200 backdrop-blur-sm flex items-center gap-2"
            >
              <Sparkles className="w-4 h-4 text-accent-cyan" />
              <span>Guided Creation</span>
            </button>
          </div>

          {/* Core Promise Pill */}
          <div className="mt-12 text-xs font-mono tracking-widest text-text-muted uppercase">
            Speak your vision. Shape the edit. Render the reel.
          </div>
        </div>
      </section>

      {/* Satyajit Ray Tribute Section */}
      <section id="tribute" className="relative py-16 border-y border-border-subtle bg-surface/40 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 items-center">
            <div className="md:col-span-1">
              <span className="text-xs font-mono text-accent-blue uppercase tracking-wider block mb-1">
                TRIBUTE EDITION
              </span>
              <h2 className="text-2xl font-bold font-cinematic text-text-primary">
                Satyajit Ray (1921–1992)
              </h2>
              <p className="text-sm text-text-secondary mt-2 leading-relaxed">
                Legendary auteur, composer, illustrator, and master of cinematic pacing. RayFlow is built around his philosophy of deliberate visual rhythm and organic human timing.
              </p>
            </div>
            <div className="md:col-span-2 p-6 rounded-2xl bg-surface-elevated/70 border border-border-medium">
              <blockquote className="text-base sm:text-lg italic font-serif text-text-primary/95 leading-relaxed">
                "The director is the only person who knows what the film will look and sound like. How images cut together, how music enters and recedes — rhythm is everything."
              </blockquote>
              <div className="mt-3 flex items-center justify-between text-xs text-text-muted">
                <span className="font-mono text-accent-cyan">— Satyajit Ray, On Filmmaking</span>
                <span className="font-mono text-text-secondary">Pather Panchali • Charulata • Nayak</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Section */}
      <section id="how-it-works" className="py-24 px-6 max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <span className="text-xs font-mono text-accent-blue uppercase tracking-widest">
            ENGINE ARCHITECTURE
          </span>
          <h2 className="text-3xl sm:text-4xl font-bold font-cinematic text-text-primary mt-2">
            Cinematic directing, automated with precision
          </h2>
          <p className="text-text-secondary text-base max-w-xl mx-auto mt-3">
            RayFlow replaces manual timeline chopping with an intelligent audio-visual compositor.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Feature 1 */}
          <div className="p-6 rounded-2xl bg-surface border border-border-subtle hover:border-accent-blue/40 transition-all duration-300 group">
            <div className="w-12 h-12 rounded-xl bg-accent-blue/10 border border-accent-blue/20 flex items-center justify-center text-accent-blue mb-5 group-hover:scale-105 transition-transform">
              <Mic className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-text-primary mb-2">Voice Direction</h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              Speak creative instructions naturally. RayFlow interprets duration, pacing, and style changes deterministically.
            </p>
          </div>

          {/* Feature 2 */}
          <div className="p-6 rounded-2xl bg-surface border border-border-subtle hover:border-accent-violet/40 transition-all duration-300 group">
            <div className="w-12 h-12 rounded-xl bg-accent-violet/10 border border-accent-violet/20 flex items-center justify-center text-accent-violet mb-5 group-hover:scale-105 transition-transform">
              <Music className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-text-primary mb-2">Beat Synchronization</h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              Real Librosa audio analysis detects tempo, transients, and strong beats, aligning cuts to musical cadence.
            </p>
          </div>

          {/* Feature 3 */}
          <div className="p-6 rounded-2xl bg-surface border border-border-subtle hover:border-accent-cyan/40 transition-all duration-300 group">
            <div className="w-12 h-12 rounded-xl bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center text-accent-cyan mb-5 group-hover:scale-105 transition-transform">
              <Video className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-text-primary mb-2">Kinetic Motion</h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              Subtle Ken Burns zoom-ins, smooth pans, and crossfades turn still photography into cinematic camera motion.
            </p>
          </div>

          {/* Feature 4 */}
          <div className="p-6 rounded-2xl bg-surface border border-border-subtle hover:border-white/30 transition-all duration-300 group">
            <div className="w-12 h-12 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-text-primary mb-5 group-hover:scale-105 transition-transform">
              <Film className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-text-primary mb-2">FFmpeg Rendering</h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              Renders genuine 1080×1920 MP4 files encoded in H.264/AAC with electric-blue gradient typography.
            </p>
          </div>
        </div>
      </section>

      {/* Product Preview Section */}
      <section className="py-16 px-6 max-w-5xl mx-auto text-center">
        <div className="p-8 sm:p-12 rounded-3xl bg-surface-elevated/60 border border-border-medium shadow-2xl relative overflow-hidden">
          <div className="max-w-2xl mx-auto">
            <span className="text-xs font-mono text-accent-cyan uppercase tracking-widest">
              CREATIVE WORKSTATION
            </span>
            <h2 className="text-3xl font-bold font-cinematic text-text-primary mt-2">
              Ready to direct your first reel?
            </h2>
            <p className="text-text-secondary text-sm sm:text-base mt-3 mb-8">
              Open the editing studio to upload your photos, select a music track, and speak your vision.
            </p>
            <SpecularButton
              size="lg"
              radius={20}
              tint="#3B82F6"
              tintOpacity={0.15}
              lineColor="#67E8F9"
              textColor="#FFFFFF"
              onClick={onEnterStudio}
              className="font-semibold px-10 py-4 shadow-lg shadow-accent-blue/30"
            >
              Launch Editing Studio
            </SpecularButton>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6 border-t border-border-subtle text-center text-xs text-text-muted font-mono">
        <p>RayFlow AI • Tribute to Satyajit Ray • Hackathon Milestone 2026</p>
      </footer>

      {/* Guided Creation Modal with Stepper */}
      {showGuidedModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
          <div className="relative max-w-lg w-full bg-[#11131A] border border-border-medium rounded-3xl p-6 shadow-2xl">
            <button
              onClick={() => setShowGuidedModal(false)}
              className="absolute top-5 right-5 text-text-secondary hover:text-text-primary text-sm font-mono"
            >
              ✕ Close
            </button>

            <div className="mb-4">
              <span className="text-xs font-mono text-accent-cyan uppercase tracking-wider">
                GUIDED SETUP
              </span>
              <h3 className="text-xl font-bold text-text-primary">Create Your Reel</h3>
            </div>

            <Stepper
              initialStep={guidedStep}
              onStepChange={step => setGuidedStep(step)}
              onFinalStepCompleted={() => {
                setShowGuidedModal(false);
                onEnterStudio();
              }}
              backButtonText="Back"
              nextButtonText="Next"
              completeButtonText="Open Studio"
              theme="dark"
              width="100%"
              frame={false}
              accentColor="#3B82F6"
            >
              <Step title="Media">
                <div className="py-4 text-center">
                  <div className="w-14 h-14 mx-auto rounded-2xl bg-accent-blue/10 border border-accent-blue/20 flex items-center justify-center text-accent-blue mb-3">
                    <Layers className="w-7 h-7" />
                  </div>
                  <h4 className="font-semibold text-text-primary">Step 1: Choose Your Photographs</h4>
                  <p className="text-xs text-text-secondary mt-1 max-w-sm mx-auto">
                    Select 3 to 10 high-resolution photos. RayFlow will scale, crop, and apply subtle cinematic motion to each frame.
                  </p>
                </div>
              </Step>

              <Step title="Music">
                <div className="py-4 text-center">
                  <div className="w-14 h-14 mx-auto rounded-2xl bg-accent-violet/10 border border-accent-violet/20 flex items-center justify-center text-accent-violet mb-3">
                    <Music className="w-7 h-7" />
                  </div>
                  <h4 className="font-semibold text-text-primary">Step 2: Add Soundtrack</h4>
                  <p className="text-xs text-text-secondary mt-1 max-w-sm mx-auto">
                    Upload an MP3 or WAV audio track. The backend will analyze the BPM and transient beats to synchronize your cuts.
                  </p>
                </div>
              </Step>

              <Step title="Direct">
                <div className="py-4 text-center">
                  <div className="w-14 h-14 mx-auto rounded-2xl bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center text-accent-cyan mb-3">
                    <Mic className="w-7 h-7" />
                  </div>
                  <h4 className="font-semibold text-text-primary">Step 3: Direct by Voice</h4>
                  <p className="text-xs text-text-secondary mt-1 max-w-sm mx-auto">
                    Speak your vision, like "Create a 20-second cinematic travel reel with fast beat-synced cuts and electric-blue typography."
                  </p>
                </div>
              </Step>

              <Step title="Render">
                <div className="py-4 text-center">
                  <div className="w-14 h-14 mx-auto rounded-2xl bg-accent-blue/10 border border-accent-blue/20 flex items-center justify-center text-accent-blue mb-3">
                    <CheckCircle2 className="w-7 h-7" />
                  </div>
                  <h4 className="font-semibold text-text-primary">Step 4: Export Finished MP4</h4>
                  <p className="text-xs text-text-secondary mt-1 max-w-sm mx-auto">
                    Preview your reel in the interactive vertical player and download a high-definition 1080×1920 MP4 ready for Instagram or TikTok.
                  </p>
                </div>
              </Step>
            </Stepper>
          </div>
        </div>
      )}
    </div>
  );
};
export default LandingPage;
