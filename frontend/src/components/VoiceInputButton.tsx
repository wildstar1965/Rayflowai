import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Mic, MicOff } from 'lucide-react';
import './VoiceInputButton.css';

interface Props {
  disabled?: boolean;
  onTranscript: (text: string) => void;
  onSubmit: (text: string) => void;
  onError: (message: string) => void;
  onListeningChange?: (listening: boolean) => void;
}

/** One utterance per command. Interim words never execute an edit. */
export function VoiceInputButton(props: Props) {
  const latest = useRef(props);
  useLayoutEffect(() => { latest.current = props; });
  const recognition = useRef<any>(null);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  const cancel = () => {
    const active = recognition.current;
    recognition.current = null;
    active?.abort();
  };
  useEffect(() => () => cancel(), []);
  useEffect(() => {
    if (props.disabled) {
      cancel(); setListening(false); setSpeaking(false);
      latest.current.onListeningChange?.(false);
    }
  }, [props.disabled]);

  const toggle = () => {
    if (recognition.current) { recognition.current.stop(); return; }
    if (latest.current.disabled) return;
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      latest.current.onError('Voice input is unavailable in this browser. Use Chrome or Edge, or type your direction.');
      return;
    }
    const active = new SpeechRecognition();
    recognition.current = active;
    active.continuous = false;
    active.interimResults = true;
    active.lang = navigator.language || 'en-US';
    let finalText = '';
    let failed = false;
    const current = () => recognition.current === active;
    active.onstart = () => {
      if (!current()) return;
      setListening(true); latest.current.onListeningChange?.(true);
    };
    active.onspeechstart = () => { if (current()) setSpeaking(true); };
    active.onspeechend = () => { if (current()) setSpeaking(false); };
    active.onresult = (event: any) => {
      if (!current() || latest.current.disabled) return;
      const results = Array.from(event.results) as any[];
      finalText = results.filter(result => result.isFinal).map(result => result[0].transcript).join(' ').trim();
      latest.current.onTranscript(results.map(result => result[0].transcript).join(' ').trim());
    };
    active.onerror = (event: { error: string }) => {
      if (!current()) return;
      failed = true;
      const errors: Record<string, string> = {
        'not-allowed': 'Microphone access was denied. Allow microphone access in your browser and try again.',
        'service-not-allowed': 'Your browser has disabled speech recognition. Enable it or type your direction.',
        'audio-capture': 'No microphone is available. Check your input device and try again.',
        'no-speech': 'No speech was detected. Click the microphone and try again.',
        network: 'Browser speech recognition could not connect. Check your connection or type your direction.',
      };
      if (event.error !== 'aborted') latest.current.onError(errors[event.error] || 'Voice input stopped. Please try again.');
      setListening(false); setSpeaking(false); latest.current.onListeningChange?.(false);
    };
    active.onend = () => {
      if (!current()) return;
      recognition.current = null;
      setListening(false); setSpeaking(false); latest.current.onListeningChange?.(false);
      if (!failed && finalText && !latest.current.disabled) latest.current.onSubmit(finalText);
    };
    try { active.start(); }
    catch {
      cancel(); setListening(false); setSpeaking(false);
      latest.current.onListeningChange?.(false);
      latest.current.onError('The microphone could not start. Check browser permissions and try again.');
    }
  };

  return <button type="button" className={`rayflow-voice-button ${listening ? 'is-listening' : ''}`}
    disabled={props.disabled} onClick={toggle} aria-pressed={listening}
    aria-label={listening ? 'Stop listening' : 'Start voice instruction'}
    title={listening ? 'Stop listening' : 'Start voice instruction'}>
    {listening ? <><MicOff size={16} /><span className={`rayflow-voice-wave ${speaking ? 'is-speaking' : ''}`} aria-hidden="true">
      {[0, 1, 2, 3, 4].map(index => <i key={index} />)}
    </span><span className="sr-only" role="status">Listening</span></> : <Mic size={16} />}
  </button>;
}
