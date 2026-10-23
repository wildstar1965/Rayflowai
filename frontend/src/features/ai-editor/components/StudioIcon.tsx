import { ArrowRight, Brain, Camera, Check, CircleCheck, Clapperboard, Compass, Construction, Folder, Globe, Hand, Image, KeyRound, Landmark, Lightbulb, Lock, LockOpen, Map, Megaphone, MessageCircle, Orbit, Package, Palette, Pin, Ruler, Scissors, Search, Settings, Shirt, Smartphone, Sparkles, Star, Sun, Tag, Target, User, Video, Volume2, WandSparkles, X, Zap, Music } from 'lucide-react';

const icons = {
  arrow: ArrowRight, brain: Brain, camera: Camera, check: Check, complete: CircleCheck,
  clapperboard: Clapperboard, compass: Compass, construction: Construction, folder: Folder,
  globe: Globe, hand: Hand, image: Image, key: KeyRound, landmark: Landmark, lightbulb: Lightbulb,
  lock: Lock, unlock: LockOpen, map: Map, megaphone: Megaphone, chat: MessageCircle, orbit: Orbit,
  package: Package, palette: Palette, pin: Pin, ruler: Ruler, scissors: Scissors, search: Search,
  settings: Settings, shirt: Shirt, smartphone: Smartphone, sparkles: Sparkles, star: Star,
  sun: Sun, tag: Tag, target: Target, user: User, video: Video, volume: Volume2, wand: WandSparkles,
  close: X, zap: Zap, music: Music,
};
export const STUDIO_ICON_NAMES = Object.keys(icons);

// Older saved moodboards contain Unicode icons. Render those as SVG without
// rewriting the user's project document or breaking category identifiers.
const legacyIcons: Record<number, keyof typeof icons> = {
  0x1f3ac: 'clapperboard', 0x1f4f7: 'camera', 0x1f4f1: 'smartphone', 0x1f4e2: 'megaphone',
  0x2728: 'sparkles', 0x1f464: 'user', 0x1f4e6: 'package', 0x1f3a5: 'video', 0x1f4a1: 'lightbulb',
  0x1f30d: 'globe', 0x1f3a8: 'palette', 0x1f4d0: 'ruler', 0x1f3db: 'landmark', 0x1f3d7: 'construction',
  0x1f454: 'shirt', 0x1f484: 'wand', 0x1f50a: 'volume', 0x1f3b5: 'music', 0x2702: 'scissors',
  0x1f30c: 'orbit', 0x1f4c1: 'folder', 0x1f4cc: 'pin',
};
export default function StudioIcon({ name, size = 16, className = '' }: { name?: string; size?: number; className?: string }) {
  const Icon = icons[name as keyof typeof icons] || icons[legacyIcons[name?.codePointAt(0) ?? 0]] || Tag;
  return <Icon size={size} strokeWidth={1.75} aria-hidden="true" className={className} style={{ display: 'inline-block', verticalAlign: 'middle', flexShrink: 0 }} />;
}
