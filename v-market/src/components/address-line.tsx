import { useState } from 'react';
import {
  Button,
  Icon,
  Sheet,
  SheetBody,
  SheetFooter,
  SheetHeader,
  TextField,
  Typography,
} from '@v-miniapp/ui-react';

const DEFAULT_ADDRESS = 'Số 7 Bằng Lăng 1, Vinhomes Riverside';

/**
 * One compact line: where the order will be delivered. Tapping it opens a
 * sheet to edit. State is local for now — it moves to shared state and
 * the storage JSAPI once checkout needs to read it too.
 *
 * Kept narrow (60%) so it never runs under V-App's ⋯ ✕ pill, which
 * overlays the top-right without reserving layout space.
 */
export const AddressLine = () => {
  const [address, setAddress] = useState(DEFAULT_ADDRESS);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(address);

  const save = () => {
    const trimmed = draft.trim();
    if (trimmed) setAddress(trimmed);
    setOpen(false);
  };

  return (
    <>
      <button
        type="button"
        className="flex max-w-[60%] items-center gap-1"
        onClick={() => {
          setDraft(address);
          setOpen(true);
        }}>
        <Icon name="pin" size={14} className="shrink-0 text-global-basic-white" />
        <Typography
          size="x-small"
          weight="semibold"
          className="truncate text-global-basic-white">
          Giao đến: {address}
        </Typography>
        <Icon name="chevron-down" size={14} className="shrink-0 text-global-basic-white" />
      </button>

      <Sheet open={open} onBackdropClick={() => setOpen(false)}>
        <SheetHeader title="Giao đến" />
        <SheetBody>
          <TextField
            value={draft}
            onChange={setDraft}
            placeholder="Nhập địa chỉ giao hàng"
            leadingIcon={{ name: 'pin' }}
          />
        </SheetBody>
        <SheetFooter>
          <Button type="solid" theme="brand" block onClick={save}>
            Xong
          </Button>
        </SheetFooter>
      </Sheet>
    </>
  );
};
