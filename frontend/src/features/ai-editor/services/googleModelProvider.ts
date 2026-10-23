import { editorStorage } from '../runtime/storage';
export type GoogleModelProvider = 'gemini' | 'replicate';

const STORAGE_KEY = 'google_model_provider_v1';

export const getGoogleModelProvider = (): GoogleModelProvider => {
  if (typeof window === 'undefined') return 'gemini';
  const stored = editorStorage.getItem(STORAGE_KEY);
  return stored === 'replicate' ? 'replicate' : 'gemini';
};

export const setGoogleModelProvider = (value: GoogleModelProvider) => {
  if (typeof window === 'undefined') return;
  editorStorage.setItem(STORAGE_KEY, value);
};

export const isReplicateGoogleProvider = () => getGoogleModelProvider() === 'replicate';
