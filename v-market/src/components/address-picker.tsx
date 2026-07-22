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
 * Sits in the navigation bar in place of a title.
 *
 * The app config object is built once and never re-read, but this is an
 * ordinary React element inside it — it owns its state and re-renders
 * itself. What the config cannot do is swap in a different element later.
 *
 * State is local for now. It moves to shared state, and to the storage
 * JSAPI rather than localStorage, once checkout needs to read it too.
 */
export const AddressPicker = () => {
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
        className="flex max-w-full items-center gap-1"
        onClick={() => {
          setDraft(address);
          setOpen(true);
        }}>
        <Icon name="pin" size={18} />
        <Typography size="base" weight="semibold" className="truncate">
          {address}
        </Typography>
        <Icon name="chevron-down" size={18} />
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
