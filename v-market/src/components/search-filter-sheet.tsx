import { useEffect, useState } from 'react';
import {
  Button,
  Dropdown,
  Sheet,
  SheetBody,
  SheetFooter,
  SheetHeader,
  Switch,
  TextField,
  Typography,
} from '@v-miniapp/ui-react';
import { CATEGORIES } from '@/lib/categories';
import {
  EMPTY_SEARCH_FILTERS,
  setSearchFilters,
  type SearchFilters,
} from '@/lib/search-query';

const parsePrice = (value: string) => {
  const digits = value.replace(/\D/g, '');
  return digits ? Number(digits) : undefined;
};

export const SearchFilterSheet = ({
  open,
  value,
  onClose,
  onApply,
}: {
  open: boolean;
  value: SearchFilters;
  onClose: () => void;
  onApply: () => void;
}) => {
  const [draft, setDraft] = useState(value);
  const [minPrice, setMinPrice] = useState(
    value.minPrice != null ? String(value.minPrice) : ''
  );
  const [maxPrice, setMaxPrice] = useState(
    value.maxPrice != null ? String(value.maxPrice) : ''
  );

  useEffect(() => {
    if (!open) return;
    setDraft(value);
    setMinPrice(value.minPrice != null ? String(value.minPrice) : '');
    setMaxPrice(value.maxPrice != null ? String(value.maxPrice) : '');
  }, [open, value]);

  const min = parsePrice(minPrice);
  const max = parsePrice(maxPrice);
  const priceError = min != null && max != null && min > max;

  const reset = () => {
    setDraft(EMPTY_SEARCH_FILTERS);
    setMinPrice('');
    setMaxPrice('');
  };

  const apply = () => {
    if (priceError) return;
    setSearchFilters({ ...draft, minPrice: min, maxPrice: max });
    onApply();
  };

  return (
    <Sheet portal open={open} onBackdropClick={onClose}>
      <SheetHeader title="Bộ lọc tìm kiếm" />
      <SheetBody>
        <div className="flex flex-col gap-4 pb-2">
          <Dropdown<string, unknown>
            label={{ text: 'Danh mục' }}
            placeholder="Tất cả danh mục"
            sheetTitle="Chọn danh mục"
            options={CATEGORIES.map(category => ({
              value: category.key,
              label: `${category.emoji}  ${category.label}`,
            }))}
            value={draft.category}
            onChange={category => setDraft(current => ({ ...current, category }))}
          />

          <div className="flex flex-col gap-2">
            <Typography size="small" weight="semibold">
              Khoảng giá
            </Typography>
            <div className="grid grid-cols-2 gap-2">
              <TextField
                value={minPrice}
                onChange={setMinPrice}
                placeholder="Từ"
                suffix="₫"
                inputMode="numeric"
                error={priceError}
              />
              <TextField
                value={maxPrice}
                onChange={setMaxPrice}
                placeholder="Đến"
                suffix="₫"
                inputMode="numeric"
                error={priceError}
              />
            </div>
            {priceError && (
              <Typography size="2x-small" className="text-global-red-red-60">
                Giá tối thiểu không được lớn hơn giá tối đa.
              </Typography>
            )}
          </div>

          <Dropdown<SearchFilters['sort'], unknown>
            label={{ text: 'Sắp xếp' }}
            options={[
              { value: 'relevance', label: 'Liên quan nhất' },
              { value: 'price-asc', label: 'Giá thấp đến cao' },
              { value: 'price-desc', label: 'Giá cao đến thấp' },
            ]}
            value={draft.sort}
            onChange={sort => setDraft(current => ({ ...current, sort }))}
          />

          <div className="flex items-center justify-between rounded-xl bg-alias-layer-01 px-3 py-3">
            <Typography size="small" weight="semibold">
              Chỉ sản phẩm đang giảm giá
            </Typography>
            <Switch
              theme="brand"
              checked={draft.onSale}
              onChange={onSale => setDraft(current => ({ ...current, onSale }))}
            />
          </div>
        </div>
      </SheetBody>
      <SheetFooter>
        <div className="flex w-full gap-2">
          <Button type="outline" theme="neutral" block onClick={reset}>
            Đặt lại
          </Button>
          <Button type="solid" theme="brand" block onClick={apply}>
            Áp dụng
          </Button>
        </div>
      </SheetFooter>
    </Sheet>
  );
};
