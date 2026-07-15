import { Search, X } from "lucide-react";
import {
  Button,
  Input,
  SearchField,
  type SearchFieldProps,
} from "react-aria-components";

interface SearchInputProps extends Omit<SearchFieldProps, "children" | "className"> {
  placeholder?: string;
}

export function SearchInput({ placeholder, ...props }: SearchInputProps) {
  return (
    <SearchField {...props} className="ds-search">
      <Search aria-hidden="true" size={16} strokeWidth={1.8} />
      <Input className="ds-search__input" placeholder={placeholder} />
      <Button aria-label="Clear search" className="ds-search__clear">
        <X aria-hidden="true" size={14} />
      </Button>
    </SearchField>
  );
}
