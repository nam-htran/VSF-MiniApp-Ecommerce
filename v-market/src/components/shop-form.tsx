import { useEffect, useState } from 'react';
import { Button, Dropdown, TextField, Toast } from '@v-miniapp/ui-react';
import { openShop, updateShop, type Shop, type ShopContact } from '@/api/shops';
import { listProvinces, type AdminUnit } from '@/api/geo';

/**
 * Open or edit a shop. Same fields either way — name, description, and the
 * contact/origin (province, address, phone) that the product page uses to
 * show where an item ships from and estimate delivery time. Province is a
 * picker, kept structured so the estimate doesn't have to parse a string.
 */
export const ShopForm = ({
  shop,
  onSaved,
}: {
  shop?: Shop;
  onSaved: () => void;
}) => {
  const editing = shop !== undefined;

  const [name, setName] = useState(shop?.name ?? '');
  const [description, setDescription] = useState(shop?.description ?? '');
  const [province, setProvince] = useState<string | undefined>(
    shop?.province ?? undefined
  );
  const [address, setAddress] = useState(shop?.address ?? '');
  const [phone, setPhone] = useState(shop?.phone ?? '');
  const [provinces, setProvinces] = useState<AdminUnit[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listProvinces()
      .then(setProvinces)
      .catch(() => setProvinces([]));
  }, []);

  const valid = name.trim().length >= 1 && description.trim().length >= 1;

  const save = async () => {
    if (!valid || saving) return;
    setSaving(true);
    const body: ShopContact = {
      name: name.trim(),
      description: description.trim(),
      province: province ?? null,
      address: address.trim() || null,
      phone: phone.trim() || null,
    };
    try {
      if (editing) await updateShop(shop.id, body);
      else await openShop(body);
      Toast.show({
        type: 'positive',
        message: editing ? 'Đã cập nhật cửa hàng' : 'Đã mở cửa hàng!',
        position: 'bottom',
      });
      onSaved();
    } catch (error) {
      Toast.show({
        type: 'negative',
        message: error instanceof Error ? error.message : 'Không lưu được',
        position: 'bottom',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <TextField value={name} onChange={setName} placeholder="Tên cửa hàng" />
      <TextField
        value={description}
        onChange={setDescription}
        placeholder="Giới thiệu ngắn về cửa hàng"
      />
      {/* Province drives the delivery estimate; the picker keeps it exact. */}
      <Dropdown
        placeholder="Tỉnh / Thành phố (để ước tính giao hàng)"
        sheetTitle="Chọn Tỉnh / Thành phố"
        allowSearch
        options={provinces.map(u => ({ value: u.name, label: u.name }))}
        value={province}
        onChange={setProvince}
      />
      <TextField
        value={address}
        onChange={setAddress}
        placeholder="Địa chỉ lấy hàng (số nhà, đường, quận/huyện)"
      />
      <TextField
        value={phone}
        onChange={setPhone}
        placeholder="Số điện thoại liên hệ"
        inputMode="tel"
      />
      <Button
        type="solid"
        theme="brand"
        block
        loading={saving}
        disabled={!valid}
        onClick={save}>
        {editing ? 'Lưu thay đổi' : 'Mở cửa hàng'}
      </Button>
    </div>
  );
};
