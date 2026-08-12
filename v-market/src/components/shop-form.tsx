import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Dropdown,
  Icon,
  Image,
  TextArea,
  TextField,
  Toast,
  Typography,
} from '@v-miniapp/ui-react';
import { openShop, updateShop, type Shop, type ShopContact } from '@/api/shops';
import { listProvinces, type AdminUnit } from '@/api/geo';
import { uploadImage } from '@/api/uploads';

/**
 * Open or edit a shop. Same fields either way — a banner and a logo the
 * seller uploads, then name, description, and the contact/origin (province,
 * address, phone) the product page uses to estimate delivery. Province is a
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
  const [banner, setBanner] = useState<string | null>(shop?.imageUrl ?? null);
  const [logo, setLogo] = useState<string | null>(shop?.logoUrl ?? null);
  const [uploading, setUploading] = useState<'banner' | 'logo' | null>(null);
  const [provinces, setProvinces] = useState<AdminUnit[]>([]);
  const [saving, setSaving] = useState(false);

  const bannerInput = useRef<HTMLInputElement>(null);
  const logoInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listProvinces()
      .then(setProvinces)
      .catch(() => setProvinces([]));
  }, []);

  const valid = name.trim().length >= 1 && description.trim().length >= 1;

  const pick = async (
    file: File,
    which: 'banner' | 'logo',
    set: (url: string) => void
  ) => {
    setUploading(which);
    try {
      set(await uploadImage(file));
    } catch (error) {
      Toast.show({
        type: 'negative',
        message: error instanceof Error ? error.message : 'Tải ảnh thất bại',
        position: 'bottom',
      });
    } finally {
      setUploading(null);
    }
  };

  const save = async () => {
    if (!valid || saving) return;
    setSaving(true);
    const body: ShopContact = {
      name: name.trim(),
      description: description.trim(),
      province: province ?? null,
      address: address.trim() || null,
      phone: phone.trim() || null,
      imageUrl: banner,
      logoUrl: logo,
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
    <div className="flex flex-col gap-4">
      {/* Banner with the logo overlapping its corner — as it looks on the
          shop page. Both uploaded by the seller. */}
      <section className="flex flex-col gap-3 rounded-2xl border border-alias-border-subtle-01 bg-alias-background p-3.5">
        <span className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-global-red-red-05">
            <Icon name="image" size={17} className="text-brand" />
          </span>
          <Typography size="small" weight="bold">
            Hình ảnh cửa hàng
          </Typography>
        </span>
        <div className="relative">
        <button
          type="button"
          onClick={() => bannerInput.current?.click()}
          disabled={uploading !== null}
          className="flex h-32 w-full items-center justify-center overflow-hidden rounded-xl border border-dashed border-alias-border-subtle-01 bg-alias-layer-01 active:opacity-80">
          {uploading === 'banner' ? (
            <Icon name="loader" size={22} animation="spin" />
          ) : banner ? (
            <Image src={banner} alt="" fit="cover" className="h-32 w-full" />
          ) : (
            <span className="flex flex-col items-center gap-1">
              <Icon name="image" size={22} color="text-tertiary" />
              <Typography size="2x-small" color="text-tertiary">
                Ảnh nền cửa hàng
              </Typography>
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => logoInput.current?.click()}
          disabled={uploading !== null}
          className="absolute -bottom-2 left-3 flex size-16 items-center justify-center overflow-hidden rounded-2xl border-2 border-alias-background bg-alias-layer-01 shadow">
          {uploading === 'logo' ? (
            <Icon name="loader" size={18} animation="spin" />
          ) : logo ? (
            <Image src={logo} alt="" fit="cover" className="size-16" />
          ) : (
            <Icon name="office" size={20} color="text-tertiary" />
          )}
        </button>
        </div>
        <Typography size="2x-small" color="text-tertiary" className="pl-1 pt-1">
          Bấm vào ảnh nền hoặc logo để thay đổi. JPEG/PNG/WebP, tối đa 5MB.
        </Typography>
      </section>

      <input
        ref={bannerInput}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={event => {
          const file = event.target.files?.[0];
          if (file) void pick(file, 'banner', setBanner);
          event.target.value = '';
        }}
      />
      <input
        ref={logoInput}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={event => {
          const file = event.target.files?.[0];
          if (file) void pick(file, 'logo', setLogo);
          event.target.value = '';
        }}
      />

      <section className="flex flex-col gap-3 rounded-2xl border border-alias-border-subtle-01 bg-alias-background p-3.5">
        <span className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-global-red-red-05">
            <Icon name="office" size={17} className="text-brand" />
          </span>
          <Typography size="small" weight="bold">
            Thông tin cửa hàng
          </Typography>
        </span>
        <TextField
          label={{ text: 'Tên cửa hàng', required: true }}
          value={name}
          onChange={setName}
          placeholder="Tên hiển thị với người mua"
        />
        <TextArea
          label={{ text: 'Giới thiệu', required: true }}
          value={description}
          onChange={setDescription}
          placeholder="Bạn bán gì và cửa hàng có gì đặc biệt?"
          rows={3}
          autoHeight
        />
      </section>

      <section className="flex flex-col gap-3 rounded-2xl border border-alias-border-subtle-01 bg-alias-background p-3.5">
        <span className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-global-red-red-05">
            <Icon name="pin" size={17} className="text-brand" />
          </span>
          <Typography size="small" weight="bold">
            Địa chỉ lấy hàng
          </Typography>
        </span>
        {/* Province drives the delivery estimate; the picker keeps it exact. */}
        <Dropdown
          label={{ text: 'Tỉnh / Thành phố' }}
          placeholder="Chọn khu vực cửa hàng"
          sheetTitle="Chọn Tỉnh / Thành phố"
          allowSearch
          options={provinces.map(u => ({ value: u.name, label: u.name }))}
          value={province}
          onChange={setProvince}
        />
        <TextField
          label={{ text: 'Địa chỉ cụ thể' }}
          value={address}
          onChange={setAddress}
          placeholder="Số nhà, đường, quận/huyện"
        />
        <TextField
          label={{ text: 'Số điện thoại liên hệ' }}
          value={phone}
          onChange={setPhone}
          placeholder="Số điện thoại của cửa hàng"
          inputMode="tel"
        />
      </section>
      <Button
        type="solid"
        theme="brand"
        block
        loading={saving}
        disabled={!valid || uploading !== null}
        onClick={save}>
        {editing ? 'Lưu thay đổi' : 'Mở cửa hàng'}
      </Button>
    </div>
  );
};
