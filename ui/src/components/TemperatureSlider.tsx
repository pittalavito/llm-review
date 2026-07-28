/**
 * Range slider + live value label. min/max/step come from props so each
 * section can keep its own range (the backend accepts 0–2).
 */
interface TemperatureSliderProps {
  id?: string;
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  inputClassName?: string;
  valueClassName?: string;
}

export default function TemperatureSlider({
  id, min, max, step = 0.1, value, onChange, disabled,
  inputClassName, valueClassName,
}: TemperatureSliderProps) {
  const clamp = (raw: number) => {
    if (!Number.isFinite(raw)) return max;
    return Math.min(max, Math.max(min, raw));
  };

  return (
    <>
      <input
        id={id}
        type="range"
        className={inputClassName}
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(clamp(Number.parseFloat(e.target.value)))}
      />
      <span className={valueClassName}>{clamp(value).toFixed(1)}</span>
    </>
  );
}
