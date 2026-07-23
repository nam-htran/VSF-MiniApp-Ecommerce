import { Typography } from '@v-miniapp/ui-react';
import { CATEGORIES } from '@/lib/categories';

/**
 * A horizontal row of category chips — an emoji tile with a label, the way
 * a food-delivery home screen shows cuisines. "Tất cả" leads; tapping one
 * filters the grid below. Selection lives with the parent.
 */
export const CategoryRow = ({
  value,
  onChange,
}: {
  value: string | 'all';
  onChange: (value: string | 'all') => void;
}) => (
  <div className="flex gap-3 overflow-x-auto px-4 pb-1">
    <Chip emoji="🏷️" label="Tất cả" active={value === 'all'} onClick={() => onChange('all')} />
    {CATEGORIES.map(category => (
      <Chip
        key={category.key}
        emoji={category.emoji}
        label={category.label}
        active={value === category.key}
        onClick={() => onChange(category.key)}
      />
    ))}
  </div>
);

const Chip = ({
  emoji,
  label,
  active,
  onClick,
}: {
  emoji: string;
  label: string;
  active: boolean;
  onClick: () => void;
}) => (
  <button
    type="button"
    onClick={onClick}
    className="flex w-20 shrink-0 flex-col items-center gap-1.5">
    <span
      className={`flex size-[72px] items-center justify-center rounded-full text-4xl transition-colors ${
        active ? 'bg-brand/10 ring-2 ring-brand' : 'bg-alias-layer-01'
      }`}>
      {emoji}
    </span>
    <Typography
      size="small"
      weight={active ? 'semibold' : 'regular'}
      color={active ? undefined : 'text-secondary'}
      className={`line-clamp-1 text-center ${active ? 'text-brand' : ''}`}>
      {label}
    </Typography>
  </button>
);
