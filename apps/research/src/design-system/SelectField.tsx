import { Check, ChevronDown } from "lucide-react";
import {
  Button,
  ListBox,
  ListBoxItem,
  Popover,
  Select,
  SelectValue,
  type Key,
} from "react-aria-components";

export interface SelectOption<T extends string> {
  value: T;
  label: string;
}

export function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly SelectOption<T>[];
  onChange: (value: T) => void;
}) {
  return (
    <Select
      aria-label={label}
      className="ds-select"
      selectedKey={value}
      onSelectionChange={(key: Key | null) => {
        if (typeof key === "string") onChange(key as T);
      }}
    >
      <Button className="ds-select__trigger">
        <SelectValue />
        <ChevronDown aria-hidden="true" size={14} />
      </Button>
      <Popover className="ds-select__popover" placement="bottom end">
        <ListBox className="ds-select__list" items={options}>
          {(option) => (
            <ListBoxItem className="ds-select__option" id={option.value} textValue={option.label}>
              {({ isSelected }) => (
                <>
                  <span>{option.label}</span>
                  {isSelected && <Check aria-hidden="true" size={14} />}
                </>
              )}
            </ListBoxItem>
          )}
        </ListBox>
      </Popover>
    </Select>
  );
}
