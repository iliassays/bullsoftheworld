import {
  ToggleButton,
  ToggleButtonGroup,
  type Key,
} from "react-aria-components";

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  count?: number;
}

export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly SegmentOption<T>[];
  onChange: (value: T) => void;
}) {
  return (
    <ToggleButtonGroup
      aria-label={label}
      className="ds-segmented"
      selectionMode="single"
      disallowEmptySelection
      selectedKeys={new Set<Key>([value])}
      onSelectionChange={(keys) => {
        const next = [...keys][0];
        if (typeof next === "string") onChange(next as T);
      }}
    >
      {options.map((option) => (
        <ToggleButton className="ds-segmented__item" id={option.value} key={option.value}>
          <span>{option.label}</span>
          {option.count !== undefined && <span className="ds-segmented__count">{option.count}</span>}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}
