import type { SubtitleSegment } from '../types';
import { transliterateToken } from './captionEngine/devanagari';
import { transliterateKannadaToken } from './captionEngine/kannada';

// Apply each engine only to its own script runs, protecting Latin loanwords even
// inside a mixed token. Unsupported scripts are retained, never approximated.
export function romanizeText(text: string): string {
  return text.replace(/[\u0900-\u097f\ua8e0-\ua8ff\u200c\u200d]+/g, transliterateToken)
    .replace(/[\u0c80-\u0cff\u200c\u200d]+/g, transliterateKannadaToken);
}

export function romanizeCaptions(segments: SubtitleSegment[]): SubtitleSegment[] {
  return segments.map(segment => {
    const text = romanizeText(segment.text);
    if (text === segment.text) return segment;
    return {...segment, text, origin: 'manual', words: segment.words?.map(word => ({...word, word: romanizeText(word.word)}))};
  });
}
