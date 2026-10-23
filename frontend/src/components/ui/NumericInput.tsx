import { useId, useState, type InputHTMLAttributes } from 'react';

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'defaultValue' | 'onChange' | 'type'> & {
  value: number;
  onCommit: (value: number) => void;
};

const numberText = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i;
const parseDraft = (text: string) => numberText.test(text.trim()) ? Number(text) : NaN;
const decimalPlaces = (value: number) => {
  const [coefficient, exponent = '0'] = String(value).split('e');
  return Math.max(0, (coefficient.split('.')[1]?.length ?? 0) - Number(exponent));
};

/** Drafts survive parent renders; only blur/Enter writes a single history operation.
 * Keep the owning field's React key tied to its entity, never its numeric value.
 */
export function NumericInput({ value, onCommit, min, max, step = 1, onBlur, onKeyDown, readOnly, disabled,
  'aria-describedby': describedBy, ...props }: Props) {
  const [draft, setDraft] = useState<string | null>(null);
  const [feedback, setFeedback] = useState('');
  const feedbackId = useId();
  const lower = min !== undefined && Number.isFinite(Number(min)) ? Number(min) : -Infinity;
  const upper = max !== undefined && Number.isFinite(Number(max)) ? Number(max) : Infinity;
  const increment = step === 'any' ? 0 : Number.isFinite(Number(step)) && Number(step) > 0 ? Number(step) : 1;

  const normalize = (parsed: number): number | null => {
    if (!Number.isFinite(parsed) || lower > upper) return null;
    let next = Math.max(lower, Math.min(upper, parsed));
    if (increment > 0) {
      const base = Number.isFinite(lower) ? lower : 0;
      // Bound the step index, not the rounded value: max can lie between steps.
      const index = Math.min(
        Math.floor((upper - base) / increment + 1e-9),
        Math.max(Math.ceil((lower - base) / increment - 1e-9), Math.round((next - base) / increment)),
      );
      next = base + index * increment;
      const precision = Math.min(100, Math.max(decimalPlaces(base), decimalPlaces(increment)));
      next = Number(next.toFixed(precision));
    }
    // Arithmetic can overflow even when the typed value is finite.
    return Number.isFinite(next) && next >= lower && next <= upper ? next : null;
  };

  const commit = (text: string) => {
    const parsed = parseDraft(text);
    const next = normalize(parsed);
    if (next === null) {
      setFeedback('Enter a finite number within this field\'s range and step. The previous value was kept.');
      setDraft(null);
      return;
    }
    setFeedback(next !== parsed ? `Adjusted to ${next} for this field's range and step.` : '');
    setDraft(null);
    if (next !== value) onCommit(next);
  };

  const displayed = draft ?? String(value);
  const displayedNumber = parseDraft(displayed);
  return <>
    <input {...props} readOnly={readOnly} disabled={disabled} type="text" inputMode={increment === 1 && lower >= 0 ? 'numeric' : 'decimal'}
      role="spinbutton" aria-valuenow={Number.isFinite(displayedNumber) ? displayedNumber : undefined}
      aria-valuetext={displayed}
      aria-valuemin={Number.isFinite(lower) ? lower : undefined}
      aria-valuemax={Number.isFinite(upper) ? upper : undefined}
      aria-describedby={[describedBy, feedback ? feedbackId : ''].filter(Boolean).join(' ') || undefined}
      value={displayed}
      onChange={event => { setDraft(event.target.value); setFeedback(''); }}
      onBlur={event => { if (draft !== null && !readOnly && !disabled) commit(draft); onBlur?.(event); }}
      onKeyDown={event => {
        onKeyDown?.(event);
        if (event.defaultPrevented || event.nativeEvent.isComposing || readOnly || disabled) return;
        if (event.key === 'Enter') {
          event.preventDefault(); event.stopPropagation();
          if (draft !== null) commit(draft);
        } else if (event.key === 'Escape') {
          event.preventDefault(); event.stopPropagation(); setDraft(null); setFeedback('');
        } else if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
          event.preventDefault(); event.stopPropagation();
          const parsed = draft === null ? value : parseDraft(draft);
          const next = normalize((Number.isFinite(parsed) ? parsed : value) + (event.key === 'ArrowUp' ? 1 : -1) * (increment || 1));
          if (next !== null) { setDraft(String(next)); setFeedback(''); }
        }
      }} />
    {feedback && <span id={feedbackId} role="status" className="block text-xs text-brass">{feedback}</span>}
  </>;
}
