import React from 'react';
import { Navbar } from '../components/ui/Navbar';
import { Button } from '../components/ui/Button';
import {
  Mic,
  Music2,
  Film,
  Download,
  ArrowRight,
  Sliders,
  Sparkles,
  Layers,
  CheckCircle2
} from 'lucide-react';

interface LandingPageProps {
  onEnterStudio: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onEnterStudio }) => {
  return (
    <div className="min-h-screen bg-white text-zinc-900 selection:bg-zinc-900 selection:text-white">
      {/* Navbar */}
      <Navbar onEnterStudio={onEnterStudio} />

      {/* Hero Section */}
      <section id="overview" className="max-w-4xl mx-auto px-5 pt-20 pb-16 text-center">
        {/* Subtle status tag */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-zinc-100 border border-zinc-200 text-xs font-medium text-zinc-700 mb-8">
          <span className="w-1.5 h-1.5 rounded-full bg-zinc-900" />
          <span>Cinematic Reel Workstation</span>
        </div>

        {/* Clean, high-quality sans-serif typography */}
        <h1 className="text-4xl sm:text-6xl md:text-7xl font-bold tracking-tight text-zinc-950 leading-[1.1]">
          Your footage. Your vision. Your voice.
        </h1>

        {/* Concise supporting description */}
        <p className="mt-6 text-base sm:text-lg text-zinc-600 max-w-2xl mx-auto font-normal leading-relaxed">
          RayFlow AI turns your photographs and soundtrack into beat-synchronized cinematic reels.
          Direct your cut timing, pacing, and titles naturally through voice or text instructions,
          and export an authentic 1080×1920 MP4 video.
        </p>

        {/* Actions */}
        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Button variant="primary" size="lg" onClick={onEnterStudio}>
            <span>Open Studio</span>
            <ArrowRight className="w-4 h-4" />
          </Button>

          <a href="#workflow">
            <Button variant="secondary" size="lg">
              <span>How It Works</span>
            </Button>
          </a>
        </div>

        {/* Subtle Notion-style Studio Preview Card */}
        <div className="mt-16 rounded-2xl border border-zinc-200 bg-zinc-50 p-3 sm:p-4 text-left shadow-sm">
          <div className="rounded-xl border border-zinc-200 bg-white p-4 sm:p-6 flex flex-col md:flex-row gap-6 items-center">
            {/* Visual 9:16 Mock */}
            <div className="w-36 sm:w-44 aspect-[9/16] rounded-lg border border-zinc-200 bg-zinc-900 text-white flex flex-col justify-between p-3 shrink-0 shadow-sm">
              <div className="flex items-center justify-between text-[10px] text-zinc-400 font-mono">
                <span>9:16 REEL</span>
                <span>30 FPS</span>
              </div>
              <div className="text-center my-auto">
                <span className="text-[11px] font-semibold tracking-wider block text-zinc-200">
                  RAYFLOW
                </span>
                <span className="text-[9px] text-zinc-400">Cinematic Cut</span>
              </div>
              <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
                <div className="w-2/3 h-full bg-zinc-200" />
              </div>
            </div>

            {/* Quick Summary Info */}
            <div className="flex-1 space-y-4">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-zinc-900" />
                <h3 className="text-sm font-semibold text-zinc-900">
                  Editing Studio Workspace
                </h3>
              </div>
              <p className="text-xs text-zinc-600 leading-relaxed">
                Organized creative environment inspired by Notion's simplicity and Apple's focus.
                Manage your photos, monitor beat markers, speak directives to the editing assistant,
                and review your real-time 9:16 preview.
              </p>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 pt-2 border-t border-zinc-100">
                <div className="p-2.5 rounded-lg bg-zinc-50 border border-zinc-200">
                  <span className="text-[10px] text-zinc-500 uppercase tracking-wider block">Aspect Ratio</span>
                  <span className="text-xs font-semibold text-zinc-900">Vertical (9:16)</span>
                </div>
                <div className="p-2.5 rounded-lg bg-zinc-50 border border-zinc-200">
                  <span className="text-[10px] text-zinc-500 uppercase tracking-wider block">Audio Sync</span>
                  <span className="text-xs font-semibold text-zinc-900">Librosa Beats</span>
                </div>
                <div className="p-2.5 rounded-lg bg-zinc-50 border border-zinc-200 col-span-2 sm:col-span-1">
                  <span className="text-[10px] text-zinc-500 uppercase tracking-wider block">Export Engine</span>
                  <span className="text-xs font-semibold text-zinc-900">FFmpeg 1080p</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Workflow Section */}
      <section id="workflow" className="border-t border-zinc-200 bg-zinc-50/60 py-20 px-5">
        <div className="max-w-5xl mx-auto">
          <div className="text-center max-w-xl mx-auto mb-14">
            <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
              Editing Workflow
            </span>
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-zinc-900 mt-2">
              Four simple steps to your finished reel
            </h2>
            <p className="text-sm text-zinc-600 mt-2">
              RayFlow handles the tedious timeline chopping so you can focus on creative direction.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              {
                step: '01',
                title: 'Add Media',
                description: 'Upload your high-resolution photos. RayFlow positions them across the multi-track timeline.',
                icon: Layers,
              },
              {
                step: '02',
                title: 'Upload Music',
                description: 'Add an audio track. Backend Librosa analysis detects tempo (BPM) and transient beat markers.',
                icon: Music2,
              },
              {
                step: '03',
                title: 'Direct by Voice',
                description: 'Speak directions like "Sync cuts to beats" or "Make the first photo last three seconds".',
                icon: Mic,
              },
              {
                step: '04',
                title: 'Export Reel',
                description: 'Preview the synchronized playback and download a genuine 1080×1920 MP4 encoded via FFmpeg.',
                icon: Film,
              },
            ].map(item => (
              <div
                key={item.step}
                className="p-5 rounded-xl bg-white border border-zinc-200 shadow-sm flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-xs font-mono font-semibold text-zinc-400">
                      {item.step}
                    </span>
                    <item.icon className="w-4 h-4 text-zinc-700" />
                  </div>
                  <h3 className="text-sm font-semibold text-zinc-900 mb-1.5">
                    {item.title}
                  </h3>
                  <p className="text-xs text-zinc-600 leading-relaxed">
                    {item.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Feature Section */}
      <section id="features" className="py-20 px-5 max-w-5xl mx-auto">
        <div className="text-center max-w-xl mx-auto mb-14">
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
            Capabilities
          </span>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-zinc-900 mt-2">
            Engineered for precision and clarity
          </h2>
          <p className="text-sm text-zinc-600 mt-2">
            Everything required to produce polished vertical reels without complex editing software.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Feature 1 */}
          <div className="p-6 rounded-xl border border-zinc-200 bg-white shadow-sm flex gap-4">
            <div className="w-9 h-9 rounded-lg bg-zinc-100 border border-zinc-200 flex items-center justify-center text-zinc-800 shrink-0">
              <Mic className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-900 mb-1">
                Deterministic Natural-Language Interpreter
              </h3>
              <p className="text-xs text-zinc-600 leading-relaxed">
                Direct duration, cut pacing, motion effects, and title overlays with plain speech or text.
                Follow-up instructions adapt the existing project without restarting your progress.
              </p>
            </div>
          </div>

          {/* Feature 2 */}
          <div className="p-6 rounded-xl border border-zinc-200 bg-white shadow-sm flex gap-4">
            <div className="w-9 h-9 rounded-lg bg-zinc-100 border border-zinc-200 flex items-center justify-center text-zinc-800 shrink-0">
              <Music2 className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-900 mb-1">
                Acoustic Beat Detection & Sync
              </h3>
              <p className="text-xs text-zinc-600 leading-relaxed">
                Powered by Librosa in Python. Automatically estimates tempo, identifies strong rhythmic transients,
                and places cut boundaries directly on musical downbeats.
              </p>
            </div>
          </div>

          {/* Feature 3 */}
          <div className="p-6 rounded-xl border border-zinc-200 bg-white shadow-sm flex gap-4">
            <div className="w-9 h-9 rounded-lg bg-zinc-100 border border-zinc-200 flex items-center justify-center text-zinc-800 shrink-0">
              <Film className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-900 mb-1">
                Kinetic Motion & Curated Color Grading
              </h3>
              <p className="text-xs text-zinc-600 leading-relaxed">
                Transform still images into dynamic shots with smooth Ken Burns zoom-ins, zoom-outs,
                and curated cinematic filters (Director, Noir, Vintage, Vibrant, Minimal).
              </p>
            </div>
          </div>

          {/* Feature 4 */}
          <div className="p-6 rounded-xl border border-zinc-200 bg-white shadow-sm flex gap-4">
            <div className="w-9 h-9 rounded-lg bg-zinc-100 border border-zinc-200 flex items-center justify-center text-zinc-800 shrink-0">
              <Download className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-900 mb-1">
                Genuine FFmpeg Video Export
              </h3>
              <p className="text-xs text-zinc-600 leading-relaxed">
                Encodes high-definition 1080×1920 MP4 files at 30 FPS using H.264 video and AAC audio.
                Download verifiable, playable video files ready for social publishing.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* About Section - Restrained inspiration acknowledgment */}
      <section id="about" className="border-t border-zinc-200 bg-zinc-50/50 py-16 px-5">
        <div className="max-w-3xl mx-auto text-center space-y-3">
          <span className="text-xs font-mono text-zinc-400 uppercase tracking-wider">
            Philosophy
          </span>
          <h2 className="text-xl font-semibold text-zinc-900">
            Pacing, rhythm, and human vision
          </h2>
          <p className="text-xs sm:text-sm text-zinc-600 leading-relaxed max-w-xl mx-auto">
            RayFlow AI is guided by filmmaker Satyajit Ray's insight: "The director is the only person
            who knows what the film will look and sound like. How images cut together, how music enters
            and recedes — rhythm is everything."
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-zinc-200 py-8 px-5 bg-white text-center text-xs text-zinc-500">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-zinc-900" />
            <span className="font-semibold text-zinc-900">RayFlow AI</span>
            <span className="text-zinc-400">• Production Reel Studio</span>
          </div>
          <div className="flex items-center gap-6 text-zinc-500">
            <a href="#overview" className="hover:text-zinc-900 transition-colors">Overview</a>
            <a href="#workflow" className="hover:text-zinc-900 transition-colors">Workflow</a>
            <a href="#features" className="hover:text-zinc-900 transition-colors">Features</a>
            <button onClick={onEnterStudio} className="hover:text-zinc-900 font-medium transition-colors">
              Launch Studio
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
