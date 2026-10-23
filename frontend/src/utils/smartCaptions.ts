// Adapted from splitWordsIntoSubtitleSegments in AI Video Production Editor/src/App.tsx.
// Copyright (C) 2026 Ludwig Maximillian Kienle. GPL-3.0-or-later.
// See ../vendor/aivpe/NOTICE and LICENSE. Rayflow adaptation preserves styling,
// bounds and word metadata, and prevents short-tail merging from exceeding limits.
import type { SubtitleSegment, WordTiming } from '../types';

export function splitWordsIntoSubtitleSegments(words: WordTiming[], start: number, end: number): WordTiming[][] {
  const clean = words.filter(word => word.word.trim() && Number.isFinite(word.start) && Number.isFinite(word.end))
    .map(word => ({ ...word, start: Math.max(start, word.start), end: Math.min(end, word.end) }))
    .filter(word => word.end > word.start).sort((a, b) => a.start - b.start);
  const segments: WordTiming[][] = [];
  let current: WordTiming[] = [];
  const tooLong = (group: WordTiming[]) => group.length > 11 || group.map(word => word.word).join(' ').length > 58 || group[group.length - 1].end - group[0].start > 4.8;
  clean.forEach((word, index) => {
    const candidate = [...current, word];
    if (current.length && tooLong(candidate)) { segments.push(current); current = [word]; }
    else current = candidate;
    const next = clean[index + 1];
    if ((/[.!?]$/.test(word.word) && current.length >= 4) || (/[,;:]$/.test(word.word) && current.length >= 6) || (next && next.start - word.end > .28 && current.length >= 3)) {
      segments.push(current); current = [];
    }
  });
  if (current.length) segments.push(current);
  const merged: WordTiming[][] = [];
  segments.forEach(segment => {
    const previous = merged[merged.length - 1];
    const short = segment.length < 3 || segment[segment.length - 1].end - segment[0].start < .7;
    if (previous && short && !tooLong([...previous, ...segment]) && segment[0].start - previous[previous.length - 1].end <= .28) merged[merged.length - 1] = [...previous, ...segment];
    else merged.push(segment);
  });
  return merged;
}

export function regroupCaptions(subtitles: SubtitleSegment[]): SubtitleSegment[] {
  if (!subtitles.some(segment => segment.words?.length)) throw new Error('Generate word-timed captions before using Smart phrases.');
  return subtitles.flatMap(segment => {
    if (!segment.words?.length) return [segment];
    const groups = splitWordsIntoSubtitleSegments(segment.words, segment.start_time, segment.end_time);
    return groups.length ? groups.map((words, index) => ({ ...segment, id: `${segment.id}-phrase-${index}`, text: words.map(word => word.word).join(' '), start_time: words[0].start, end_time: words[words.length - 1].end, words })) : [segment];
  });
}
