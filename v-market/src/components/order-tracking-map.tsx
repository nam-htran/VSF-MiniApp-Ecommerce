import { useEffect, useRef, useState } from 'react';
import { Typography } from '@v-miniapp/ui-react';

/**
 * A simulated delivery tracker. A real map is impossible here — third-party
 * tiles can't be whitelisted — so this is a stylised SVG: a route from the
 * warehouse to the destination with a courier marker that advances along
 * it, a stage timeline, and an ETA.
 *
 * There is no real logistics feed either, so progress is simulated from the
 * order's own age over a short demo window: a just-paid order sets off and
 * arrives a few minutes later. Clearly a mock — labelled as one.
 */
const ROUTE = 'M 20 120 C 82 116 96 42 158 54 C 214 64 252 98 302 28';
const DEMO_WINDOW_MS = 6 * 60 * 1000;
const STAGES = ['Đã xác nhận', 'Đang lấy hàng', 'Đang giao', 'Đã giao'];
// Fraction of the trip at which each stage begins.
const STAGE_STARTS = [0, 0.12, 0.4, 0.99];

const progressFrom = (createdAtMs: number) => {
  const elapsed = Date.now() - createdAtMs;
  return Math.min(1, Math.max(0, elapsed / DEMO_WINDOW_MS));
};

const stageIndex = (progress: number) => {
  let index = 0;
  for (let i = 0; i < STAGE_STARTS.length; i++) {
    if (progress >= STAGE_STARTS[i]) index = i;
  }
  return index;
};

export const OrderTrackingMap = ({ createdAt }: { createdAt: string }) => {
  const createdAtMs = new Date(createdAt).getTime();
  const [progress, setProgress] = useState(() => progressFrom(createdAtMs));
  const [point, setPoint] = useState<{ x: number; y: number } | null>(null);
  const pathRef = useRef<SVGPathElement>(null);

  // Tick while the trip is under way; stop once delivered.
  useEffect(() => {
    if (progress >= 1) return;
    const id = setInterval(() => setProgress(progressFrom(createdAtMs)), 1000);
    return () => clearInterval(id);
  }, [createdAtMs, progress]);

  // Place the marker along the path at the current progress.
  useEffect(() => {
    const path = pathRef.current;
    if (!path) return;
    const at = path.getPointAtLength(progress * path.getTotalLength());
    setPoint({ x: at.x, y: at.y });
  }, [progress]);

  const current = stageIndex(progress);
  const delivered = progress >= 1;
  const etaMinutes = Math.ceil(((1 - progress) * DEMO_WINDOW_MS) / 60000);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <Typography size="small" weight="semibold" className="text-brand">
          {STAGES[current]}
        </Typography>
        <Typography size="x-small" color="text-secondary">
          {delivered ? 'Đã giao đến bạn' : `Dự kiến ~${etaMinutes} phút`}
        </Typography>
      </div>

      {/* The stylised map. */}
      <div className="overflow-hidden rounded-xl bg-global-teal-teal-05">
        <svg viewBox="0 0 322 150" className="h-40 w-full">
          {/* decorative blocks + roads, so it reads as a map at a glance */}
          <g fill="#e2e8f0">
            <rect x="26" y="20" width="46" height="30" rx="4" />
            <rect x="120" y="14" width="60" height="26" rx="4" />
            <rect x="210" y="70" width="54" height="34" rx="4" />
            <rect x="40" y="86" width="52" height="40" rx="4" />
          </g>
          <g stroke="#e2e8f0" strokeWidth="6" strokeLinecap="round">
            <line x1="0" y1="70" x2="322" y2="70" />
            <line x1="180" y1="0" x2="180" y2="150" />
          </g>

          {/* the route: full length in grey, traveled portion in brand */}
          <path d={ROUTE} fill="none" stroke="#cbd5e1" strokeWidth="4" strokeLinecap="round" />
          <path
            ref={pathRef}
            d={ROUTE}
            fill="none"
            stroke="#e31c23"
            strokeWidth="4"
            strokeLinecap="round"
            pathLength={100}
            strokeDasharray={100}
            strokeDashoffset={100 - progress * 100}
          />

          {/* endpoints */}
          <circle cx="20" cy="120" r="6" fill="#ffffff" stroke="#94a3b8" strokeWidth="2.5" />
          <text x="20" y="140" textAnchor="middle" fontSize="9" fill="#64748b">
            Kho
          </text>
          <text x="302" y="18" textAnchor="middle" fontSize="14">
            🏠
          </text>

          {/* the courier */}
          {point && (
            <g transform={`translate(${point.x}, ${point.y})`}>
              <circle r="12" fill="#ffffff" stroke="#e31c23" strokeWidth="2" />
              <text textAnchor="middle" dominantBaseline="central" fontSize="14">
                🛵
              </text>
            </g>
          )}
        </svg>
      </div>

      {/* stage timeline */}
      <div className="relative pt-1">
        <div className="absolute left-[12.5%] right-[12.5%] top-3 h-0.5 bg-alias-border-subtle-01" />
        <div
          className="absolute left-[12.5%] top-3 h-0.5 bg-brand transition-all duration-500"
          style={{ width: `${(current / 3) * 75}%` }}
        />
        <div className="relative flex">
          {STAGES.map((stage, i) => (
            <div key={stage} className="flex flex-1 flex-col items-center gap-1">
              <span
                className={`size-4 rounded-full border-2 ${
                  i <= current
                    ? 'border-brand bg-brand'
                    : 'border-alias-border-subtle-01 bg-alias-background'
                }`}
              />
              <Typography
                size="2x-small"
                weight={i === current ? 'semibold' : 'regular'}
                color={i <= current ? 'text-primary' : 'text-tertiary'}
                className="text-center">
                {stage}
              </Typography>
            </div>
          ))}
        </div>
      </div>

      <Typography size="2x-small" color="text-tertiary" className="text-center">
        Bản đồ theo dõi là mô phỏng cho demo.
      </Typography>
    </div>
  );
};
