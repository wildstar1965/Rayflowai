import { useEffect, useState } from 'react';
import { creativeRequest } from '../../services/api';

interface Model {
  id: string; label: string; status: 'missing' | 'unverified' | 'checking' | 'ready' | 'failed';
  message: string; device?: string; compute_type?: string; notice?: string;
}
interface Catalog { models: Model[]; checking: boolean; default_model: string | null; notice: string; performance: string }

export function useSpeechModels() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll(first = false) {
      try {
        const data = await creativeRequest<Catalog>(first ? '/captions/models/check' : '/captions/models', first ? {} : undefined, abort.signal);
        if (abort.signal.aborted) return;
        setCatalog(data); setError('');
        if (data.checking) timer = setTimeout(() => void poll(), 1000);
      } catch (error) {
        if (!abort.signal.aborted) setError(error instanceof Error ? error.message : 'Could not check local models.');
      }
    }
    void poll(true);
    return () => { abort.abort(); clearTimeout(timer); };
  }, [revision]);
  return { catalog, error, refresh: () => setRevision(value => value + 1) };
}

