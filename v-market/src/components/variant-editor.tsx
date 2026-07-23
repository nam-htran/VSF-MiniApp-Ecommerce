import { useMemo, useState } from 'react';
import { Button, Icon, TextField, Typography } from '@v-miniapp/ui-react';

/**
 * Where a seller defines what a product comes in — "Size: M, L, XL",
 * "Màu sắc: Đen, Trắng" — and how many of each combination they hold.
 *
 * The seller types the group names, so a shop selling paint writes "Dung
 * tích" and nothing here changes. Combinations are generated from the
 * groups rather than typed one by one: two groups of four values is
 * sixteen rows nobody wants to enter by hand.
 *
 * Quantities are the point. Once a product has options its stock lives
 * only here, so an empty box means none of that size — not "unlimited".
 */
export type DraftVariant = {
  options: Record<string, string>;
  stock: number;
  price?: number | null;
};

type Group = { name: string; values: string[] };

/** Every combination of the groups, in the order the seller typed them. */
const combine = (groups: Group[]): Record<string, string>[] => {
  const usable = groups.filter(g => g.name.trim() && g.values.length > 0);
  if (usable.length === 0) return [];
  return usable.reduce<Record<string, string>[]>(
    (rows, group) =>
      rows.flatMap(row =>
        group.values.map(value => ({ ...row, [group.name.trim()]: value }))
      ),
    [{}]
  );
};

const keyOf = (options: Record<string, string>) =>
  Object.entries(options)
    .map(([group, value]) => `${group}=${value}`)
    .join('|');

export const VariantEditor = ({
  value,
  onChange,
}: {
  value: DraftVariant[];
  onChange: (variants: DraftVariant[]) => void;
}) => {
  // Groups are derived from the variants on first render so editing an
  // existing product shows what it already has.
  const [groups, setGroups] = useState<Group[]>(() => {
    const found = new Map<string, string[]>();
    for (const variant of value) {
      for (const [group, val] of Object.entries(variant.options)) {
        const values = found.get(group) ?? [];
        if (!values.includes(val)) values.push(val);
        found.set(group, values);
      }
    }
    return [...found.entries()].map(([name, values]) => ({ name, values }));
  });
  const [draftValue, setDraftValue] = useState<Record<number, string>>({});

  const rows = useMemo(() => combine(groups), [groups]);

  // Quantities already entered, kept across regeneration so adding a colour
  // doesn't wipe the sizes the seller just typed.
  const stockByKey = useMemo(() => {
    const map = new Map<string, DraftVariant>();
    for (const variant of value) map.set(keyOf(variant.options), variant);
    return map;
  }, [value]);

  const push = (nextRows: Record<string, string>[]) =>
    onChange(
      nextRows.map(options => ({
        options,
        stock: stockByKey.get(keyOf(options))?.stock ?? 0,
        price: stockByKey.get(keyOf(options))?.price ?? null,
      }))
    );

  const editGroups = (next: Group[]) => {
    setGroups(next);
    push(combine(next));
  };

  const setStock = (options: Record<string, string>, stock: number) =>
    onChange(
      rows.map(row => {
        const existing = stockByKey.get(keyOf(row));
        return keyOf(row) === keyOf(options)
          ? { options: row, stock, price: existing?.price ?? null }
          : {
              options: row,
              stock: existing?.stock ?? 0,
              price: existing?.price ?? null,
            };
      })
    );

  return (
    <div className="flex flex-col gap-3 rounded-xl bg-alias-layer-01 p-3">
      <div className="flex items-center justify-between">
        <Typography size="small" weight="bold">
          Phân loại
        </Typography>
        <Button
          shape="pill"
          type="ghost"
          theme="brand"
          size="medium"
          onClick={() => editGroups([...groups, { name: '', values: [] }])}>
          <span className="flex items-center gap-1">
            <Icon name="plus" size={14} />
            Thêm nhóm
          </span>
        </Button>
      </div>

      {groups.length === 0 && (
        <Typography size="2x-small" color="text-tertiary">
          Không bắt buộc. Bỏ trống nếu sản phẩm chỉ có một loại — khi đó tồn
          kho lấy theo ô "Số lượng" ở trên.
        </Typography>
      )}

      {groups.map((group, index) => (
        <div key={index} className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <TextField
              value={group.name}
              onChange={name =>
                editGroups(groups.map((g, i) => (i === index ? { ...g, name } : g)))
              }
              placeholder="Tên nhóm, ví dụ Size hoặc Màu sắc"
              className="flex-1"
            />
            <button
              type="button"
              aria-label="Xoá nhóm"
              onClick={() => editGroups(groups.filter((_, i) => i !== index))}
              className="p-1">
              <Icon name="trash" size={16} color="text-tertiary" />
            </button>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {group.values.map(val => (
              <span
                key={val}
                className="flex items-center gap-1 rounded-full bg-alias-background px-2.5 py-1">
                <Typography size="2x-small">{val}</Typography>
                <button
                  type="button"
                  aria-label={`Xoá ${val}`}
                  onClick={() =>
                    editGroups(
                      groups.map((g, i) =>
                        i === index
                          ? { ...g, values: g.values.filter(v => v !== val) }
                          : g
                      )
                    )
                  }>
                  <Icon name="xmark" size={11} color="text-tertiary" />
                </button>
              </span>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <TextField
              value={draftValue[index] ?? ''}
              onChange={text => setDraftValue({ ...draftValue, [index]: text })}
              placeholder="Thêm giá trị rồi bấm +"
              className="flex-1"
            />
            <Button
              shape="pill"
              type="outline"
              size="medium"
              onClick={() => {
                const text = (draftValue[index] ?? '').trim();
                if (!text || group.values.includes(text)) return;
                editGroups(
                  groups.map((g, i) =>
                    i === index ? { ...g, values: [...g.values, text] } : g
                  )
                );
                setDraftValue({ ...draftValue, [index]: '' });
              }}>
              Thêm
            </Button>
          </div>
        </div>
      ))}

      {rows.length > 0 && (
        <div className="flex flex-col gap-1.5 border-t border-alias-border-subtle-01 pt-2">
          <Typography size="2x-small" color="text-tertiary">
            Số lượng từng loại — để 0 nghĩa là hết hàng loại đó.
          </Typography>
          {rows.map(options => {
            const label = Object.values(options).join(' / ');
            const current = stockByKey.get(keyOf(options));
            return (
              <div key={keyOf(options)} className="flex items-center gap-2">
                <Typography size="x-small" className="flex-1 truncate">
                  {label}
                </Typography>
                <div className="w-24">
                  <TextField
                    value={String(current?.stock ?? 0)}
                    onChange={text =>
                      setStock(options, Math.max(0, Number(text) || 0))
                    }
                    inputMode="numeric"
                    placeholder="0"
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
