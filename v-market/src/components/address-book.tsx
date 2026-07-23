import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Dropdown,
  Icon,
  Sheet,
  SheetBody,
  SheetHeader,
  TextField,
  Toast,
  Typography,
} from '@v-miniapp/ui-react';
import {
  createAddress,
  deleteAddress,
  setDefaultAddress,
  type SavedAddress,
} from '@/api/addresses';
import {
  listDistricts,
  listProvinces,
  listWards,
  reverseGeocode,
  type AdminUnit,
} from '@/api/geo';
import { getCurrentLocation, formatPin, type GeoPin } from '@/lib/location';

/**
 * The address book, as a bottom sheet with two views:
 *  - list: the saved addresses, tap one to use it, with set-default and
 *    delete per row;
 *  - form: add a new address — recipient, phone, and the location entered
 *    structured (cascading Tỉnh → Huyện → Xã) or as one manual line, with
 *    an optional "ghim vị trí" that reverse-geocodes GPS into the field.
 * The parent owns the list and the current selection; this sheet reports
 * changes back up through onSelect / onChanged / onCreated.
 */
export const AddressBookSheet = ({
  open,
  onClose,
  addresses,
  selectedId,
  defaultRecipientName,
  defaultPhone,
  onSelect,
  onChanged,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  addresses: SavedAddress[];
  selectedId?: string;
  defaultRecipientName: string;
  defaultPhone: string;
  // Given at checkout (pick one to ship to); omitted in the account tab,
  // where the sheet only manages the book — no selection.
  onSelect?: (id: string) => void;
  onChanged: () => void;
  onCreated: (created: SavedAddress) => void;
}) => {
  const [view, setView] = useState<'list' | 'form'>('list');

  // Open straight into the form when there is nothing to pick yet.
  useEffect(() => {
    if (open) setView(addresses.length === 0 ? 'form' : 'list');
  }, [open]);

  return (
    <Sheet open={open} onBackdropClick={onClose}>
      <SheetHeader
        title={view === 'form' ? 'Thêm địa chỉ' : 'Địa chỉ của tôi'}
      />
      <SheetBody>
        {/* key by view so the list↔form swap replays the fade. */}
        <div key={view} className="animate-fade-in">
          {view === 'list' ? (
            <AddressList
              addresses={addresses}
              selectedId={selectedId}
              onSelect={
                onSelect
                  ? id => {
                      onSelect(id);
                      onClose();
                    }
                  : undefined
              }
              onChanged={onChanged}
              onAdd={() => setView('form')}
            />
          ) : (
            <AddressForm
              defaultRecipientName={defaultRecipientName}
              defaultPhone={defaultPhone}
              forceDefault={addresses.length === 0}
              onCancel={() =>
                addresses.length === 0 ? onClose() : setView('list')
              }
              onCreated={created => {
                onCreated(created);
                setView('list');
              }}
            />
          )}
        </div>
      </SheetBody>
    </Sheet>
  );
};

const AddressList = ({
  addresses,
  selectedId,
  onSelect,
  onChanged,
  onAdd,
}: {
  addresses: SavedAddress[];
  selectedId?: string;
  onSelect?: (id: string) => void;
  onChanged: () => void;
  onAdd: () => void;
}) => {
  const [busyId, setBusyId] = useState<string | null>(null);

  const remove = async (id: string) => {
    setBusyId(id);
    try {
      await deleteAddress(id);
      onChanged();
    } catch {
      Toast.show({ type: 'negative', message: 'Không xoá được địa chỉ', position: 'bottom' });
    } finally {
      setBusyId(null);
    }
  };

  const makeDefault = async (id: string) => {
    setBusyId(id);
    try {
      await setDefaultAddress(id);
      onChanged();
    } catch {
      Toast.show({ type: 'negative', message: 'Không đặt được mặc định', position: 'bottom' });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="flex flex-col gap-2 pb-2">
      {addresses.map(address => {
        const selectable = onSelect != null;
        const active = selectable && address.id === selectedId;
        const info = (
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="flex flex-wrap items-center gap-2">
              <Typography size="small" weight="semibold">
                {address.recipientName}
              </Typography>
              <Typography size="x-small" color="text-secondary">
                {address.phone}
              </Typography>
              {address.isDefault && (
                <span className="rounded bg-brand/10 px-1.5 py-0.5">
                  <Typography size="2x-small" weight="semibold" className="text-brand">
                    Mặc định
                  </Typography>
                </span>
              )}
            </span>
            <Typography size="x-small" color="text-secondary" className="whitespace-pre-line">
              {address.addressLine}
            </Typography>
          </div>
        );
        return (
          <div
            key={address.id}
            className={`flex flex-col gap-2 rounded-xl border p-3 ${
              active ? 'border-brand bg-global-red-red-05' : 'border-alias-border-subtle-01'
            }`}>
            {selectable ? (
              <button
                type="button"
                onClick={() => onSelect(address.id)}
                className="flex items-start gap-2.5 text-left">
                {active ? (
                  <Icon name="circle-check" type="fill" size={18} className="mt-0.5 shrink-0 text-brand" />
                ) : (
                  <span className="mt-0.5 size-[18px] shrink-0 rounded-full border-2 border-alias-border-subtle-01" />
                )}
                {info}
              </button>
            ) : (
              <div className="flex items-start gap-2.5">{info}</div>
            )}

            <div className="flex items-center gap-4 pl-7">
              {!address.isDefault && (
                <button
                  type="button"
                  disabled={busyId !== null}
                  onClick={() => makeDefault(address.id)}>
                  <Typography size="x-small" className="text-brand">
                    Đặt mặc định
                  </Typography>
                </button>
              )}
              <button
                type="button"
                disabled={busyId !== null}
                onClick={() => remove(address.id)}>
                <Typography size="x-small" color="text-secondary">
                  Xoá
                </Typography>
              </button>
            </div>
          </div>
        );
      })}

      <Button type="outline" theme="brand" block onClick={onAdd}>
        <span className="flex items-center justify-center gap-1.5">
          <Icon name="plus" size={16} />
          Thêm địa chỉ mới
        </span>
      </Button>
    </div>
  );
};

const MODE_OPTIONS: ['structured' | 'manual', string][] = [
  ['structured', 'Chọn khu vực'],
  ['manual', 'Nhập tay'],
];

const recipientOk = (name: string, phone: string) =>
  name.trim().length >= 2 && /^[0-9+\s]{8,}$/.test(phone.trim());

const nameOf = (list: AdminUnit[], code: string | undefined) =>
  list.find(u => u.code === code)?.name ?? '';

const AddressForm = ({
  defaultRecipientName,
  defaultPhone,
  forceDefault,
  onCancel,
  onCreated,
}: {
  defaultRecipientName: string;
  defaultPhone: string;
  forceDefault: boolean;
  onCancel: () => void;
  onCreated: (created: SavedAddress) => void;
}) => {
  const [name, setName] = useState(defaultRecipientName);
  const [phone, setPhone] = useState(defaultPhone);
  const [mode, setMode] = useState<'structured' | 'manual'>('structured');

  const [provinces, setProvinces] = useState<AdminUnit[]>([]);
  const [districts, setDistricts] = useState<AdminUnit[]>([]);
  const [wards, setWards] = useState<AdminUnit[]>([]);
  const [province, setProvince] = useState<string>();
  const [district, setDistrict] = useState<string>();
  const [ward, setWard] = useState<string>();
  const [street, setStreet] = useState('');

  const [manual, setManual] = useState('');

  const [pin, setPin] = useState<GeoPin | null>(null);
  const [pinning, setPinning] = useState(false);
  const [makeDefault, setMakeDefault] = useState(forceDefault);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listProvinces()
      .then(setProvinces)
      .catch(() => setProvinces([]));
  }, []);

  useEffect(() => {
    setDistrict(undefined);
    setWard(undefined);
    setDistricts([]);
    setWards([]);
    if (!province) return;
    listDistricts(province)
      .then(setDistricts)
      .catch(() => setDistricts([]));
  }, [province]);

  useEffect(() => {
    setWard(undefined);
    setWards([]);
    if (!district) return;
    listWards(district)
      .then(setWards)
      .catch(() => setWards([]));
  }, [district]);

  const addressLine = useMemo<string | null>(() => {
    let text: string;
    if (mode === 'manual') {
      if (manual.trim().length < 5) return null;
      text = manual.trim();
    } else {
      if (!province || !district || !ward || street.trim().length < 3)
        return null;
      text = `${street.trim()}, ${nameOf(wards, ward)}, ${nameOf(
        districts,
        district
      )}, ${nameOf(provinces, province)}`;
    }
    return pin ? `${text}\n📍 ${formatPin(pin)}` : text;
  }, [mode, manual, province, district, ward, street, wards, districts, provinces, pin]);

  const canSave = recipientOk(name, phone) && addressLine !== null && !saving;

  const useMyLocation = async () => {
    setPinning(true);
    try {
      const here = await getCurrentLocation();
      setPin(here);
      const { address } = await reverseGeocode(here.latitude, here.longitude);
      if (address) {
        setMode('manual');
        setManual(address);
      }
      Toast.show({
        type: 'positive',
        message: address
          ? 'Đã điền địa chỉ từ vị trí hiện tại'
          : 'Đã ghim toạ độ — nhập địa chỉ giúp nhé',
        position: 'bottom',
      });
    } catch (error) {
      Toast.show({
        type: 'informative',
        message:
          error instanceof Error
            ? error.message
            : 'Không lấy được vị trí, nhập địa chỉ thủ công nhé',
        position: 'bottom',
      });
    } finally {
      setPinning(false);
    }
  };

  const save = async () => {
    if (!addressLine || !canSave) return;
    setSaving(true);
    try {
      const created = await createAddress({
        recipientName: name.trim(),
        phone: phone.trim(),
        addressLine,
        isDefault: makeDefault,
      });
      onCreated(created);
    } catch {
      Toast.show({ type: 'negative', message: 'Không lưu được địa chỉ', position: 'bottom' });
    } finally {
      setSaving(false);
    }
  };

  const toOptions = (list: AdminUnit[]) =>
    list.map(u => ({ value: u.code, label: u.name }));

  return (
    <div className="flex flex-col gap-3 pb-2">
      <TextField value={name} onChange={setName} placeholder="Tên người nhận" />
      <TextField value={phone} onChange={setPhone} placeholder="Số điện thoại" inputMode="tel" />

      <Segmented value={mode} options={MODE_OPTIONS} onChange={setMode} />

      {/* key by mode so switching entry style fades in rather than snapping. */}
      <div key={mode} className="flex animate-fade-in flex-col gap-3">
        {mode === 'structured' ? (
          <>
            <Dropdown
              placeholder="Tỉnh / Thành phố"
              sheetTitle="Chọn Tỉnh / Thành phố"
              allowSearch
              options={toOptions(provinces)}
              value={province}
              onChange={setProvince}
            />
            <Dropdown
              placeholder="Quận / Huyện"
              sheetTitle="Chọn Quận / Huyện"
              allowSearch
              disabled={!province}
              options={toOptions(districts)}
              value={district}
              onChange={setDistrict}
            />
            <Dropdown
              placeholder="Phường / Xã"
              sheetTitle="Chọn Phường / Xã"
              allowSearch
              disabled={!district}
              options={toOptions(wards)}
              value={ward}
              onChange={setWard}
            />
            <TextField value={street} onChange={setStreet} placeholder="Số nhà, tên đường" />
          </>
        ) : (
          <TextField
            value={manual}
            onChange={setManual}
            placeholder="Địa chỉ đầy đủ: số nhà, đường, phường/xã, quận/huyện, tỉnh/thành"
          />
        )}
      </div>

      {pin ? (
        <span className="flex animate-fade-in items-center justify-between gap-2 rounded-xl bg-global-teal-teal-10 px-3 py-2">
          <span className="flex min-w-0 items-center gap-1.5">
            <Icon name="pin-tack" size={14} className="shrink-0 text-global-teal-teal-60" />
            <Typography size="x-small" className="truncate text-global-teal-teal-70">
              Đã ghim: {formatPin(pin)}
            </Typography>
          </span>
          <button type="button" aria-label="Bỏ ghim vị trí" onClick={() => setPin(null)}>
            <Icon name="xmark" size={14} color="text-tertiary" />
          </button>
        </span>
      ) : (
        <Button type="outline" theme="neutral" block loading={pinning} onClick={useMyLocation}>
          <span className="flex items-center justify-center gap-1.5">
            <Icon name="pin-tack" size={16} />
            Ghim vị trí hiện tại
          </span>
        </Button>
      )}

      <button
        type="button"
        disabled={forceDefault}
        onClick={() => setMakeDefault(v => !v)}
        className="flex items-center gap-2">
        <Icon
          name={makeDefault ? 'circle-check' : 'circle-info'}
          type={makeDefault ? 'fill' : 'outline'}
          size={18}
          className={makeDefault ? 'text-brand' : 'text-alias-icon-tertiary'}
        />
        <Typography size="small" color={forceDefault ? 'text-tertiary' : 'text-primary'}>
          Đặt làm địa chỉ mặc định
        </Typography>
      </button>

      <div className="flex gap-2 pt-1">
        <Button type="outline" theme="neutral" block onClick={onCancel}>
          Huỷ
        </Button>
        <Button type="solid" theme="brand" block loading={saving} disabled={!canSave} onClick={save}>
          Lưu địa chỉ
        </Button>
      </div>
    </div>
  );
};

/** A pill segmented control: two or more mutually exclusive text options. */
function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: [T, string][];
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex gap-1 rounded-full bg-alias-layer-01 p-1">
      {options.map(([optionValue, label]) => (
        <button
          key={optionValue}
          type="button"
          onClick={() => onChange(optionValue)}
          className={`flex-1 rounded-full py-1.5 text-center transition-colors ${
            value === optionValue ? 'bg-alias-background shadow-sm' : ''
          }`}>
          <Typography
            size="small"
            weight={value === optionValue ? 'semibold' : 'regular'}
            color={value === optionValue ? 'text-primary' : 'text-secondary'}>
            {label}
          </Typography>
        </button>
      ))}
    </div>
  );
}
