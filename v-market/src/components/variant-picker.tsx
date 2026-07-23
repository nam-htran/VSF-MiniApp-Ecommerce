import { useEffect, useMemo, useState } from 'react';
import { Image, Typography } from '@v-miniapp/ui-react';
import type { ApiVariant } from '@/api/products';
import { formatVnd } from '@/lib/format';

/**
 * The option rows on a product page — "Màu sắc", "Size" — built from the
 * variants themselves rather than a fixed schema, so a shop selling paint
 * gets "Dung tích" without any change here.
 *
 * A value is greyed and unselectable when nothing in stock matches it
 * alongside the other choices already made: picking "Đen" then seeing "L"
 * dim is the honest answer to "is there a black L?", and it beats letting
 * the buyer choose and be refused at checkout.
 */
export const VariantPicker = ({
  variants,
  onSelect,
}: {
  variants: ApiVariant[];
  /** null until every group has a choice that resolves to a real variant. */
  onSelect: (variant: ApiVariant | null) => void;
}) => {
  // Group name -> the values offered, in the seller's own order (variants
  // arrive ordered, so first-seen order is theirs).
  const groups = useMemo(() => {
    const found = new Map<string, string[]>();
    for (const variant of variants) {
      for (const [group, value] of Object.entries(variant.options)) {
        const values = found.get(group) ?? [];
        if (!values.includes(value)) values.push(value);
        found.set(group, values);
      }
    }
    return [...found.entries()];
  }, [variants]);

  const [chosen, setChosen] = useState<Record<string, string>>({});

  const match = useMemo(() => {
    if (groups.some(([group]) => !chosen[group])) return null;
    return (
      variants.find(variant =>
        Object.entries(variant.options).every(
          ([group, value]) => chosen[group] === value
        )
      ) ?? null
    );
  }, [variants, groups, chosen]);

  useEffect(() => onSelect(match), [match, onSelect]);

  /** Would picking this value still leave something in stock? */
  const reachable = (group: string, value: string) =>
    variants.some(
      variant =>
        variant.stock > 0 &&
        variant.options[group] === value &&
        // Honour the other groups already chosen, ignore this one.
        Object.entries(chosen).every(
          ([other, chosenValue]) =>
            other === group || variant.options[other] === chosenValue
        )
    );

  /** The swatch a colour chip shows, when the seller uploaded one. */
  const swatch = (group: string, value: string) =>
    variants.find(v => v.options[group] === value && v.imageUrl)?.imageUrl;

  return (
    <div className="flex flex-col gap-3">
      {groups.map(([group, values]) => (
        <div key={group} className="flex flex-col gap-1.5">
          <Typography size="x-small" color="text-secondary">
            {group}
          </Typography>
          <div className="flex flex-wrap gap-2">
            {values.map(value => {
              const available = reachable(group, value);
              const picked = chosen[group] === value;
              const thumb = swatch(group, value);
              return (
                <button
                  key={value}
                  type="button"
                  disabled={!available}
                  onClick={() =>
                    setChosen(prev =>
                      // Tapping the chosen value again clears it, so a buyer
                      // can back out of a dead end without reloading.
                      prev[group] === value
                        ? Object.fromEntries(
                            Object.entries(prev).filter(([g]) => g !== group)
                          )
                        : { ...prev, [group]: value }
                    )
                  }
                  className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 ${
                    picked
                      ? 'border-brand bg-global-red-red-10'
                      : 'border-alias-border-subtle-01 bg-alias-background'
                  } ${available ? '' : 'opacity-40'}`}>
                  {thumb && (
                    <Image
                      src={thumb}
                      alt=""
                      fit="cover"
                      className="size-6 shrink-0 rounded"
                    />
                  )}
                  <Typography
                    size="x-small"
                    weight={picked ? 'semibold' : 'regular'}
                    className={picked ? 'text-brand' : undefined}>
                    {value}
                  </Typography>
                </button>
              );
            })}
          </div>
        </div>
      ))}

      <Typography size="x-small" color="text-secondary">
        {match
          ? `Còn ${match.stock} sản phẩm${
              match.price !== null ? ` · ${formatVnd(match.price)}` : ''
            }`
          : 'Chọn phân loại để thêm vào giỏ'}
      </Typography>
    </div>
  );
};
