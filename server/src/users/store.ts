import { randomUUID } from 'node:crypto';

/**
 * Người dùng của V-Market.
 *
 * Điểm quan trọng: `role` và `sellerId` là DỮ LIỆU CỦA V-MARKET,
 * không đến từ V-App. V-App chỉ trả về danh tính (user_id) — nó không
 * có khái niệm buyer/seller. Việc ai là người bán là chuyện của V-Market.
 *
 * Ngày 1 lưu trong bộ nhớ. Ngày 2 chuyển sang DB thật cùng lúc làm
 * seed buyer / seller A / seller B.
 */

export type UserRole = 'BUYER' | 'SELLER';

export type MarketUser = {
  id: string;
  /** Khoá liên kết sang V-App. Duy nhất. */
  vappUserId: string;
  role: UserRole;
  /** Chỉ có khi role === 'SELLER'. MVP: một seller một shop. */
  sellerId: string | null;
  name: string | null;
  phoneNumber: string | null;
};

const byVAppUserId = new Map<string, MarketUser>();

/**
 * Vai trò định sẵn cho tài khoản demo. Đây là bảng của V-Market,
 * không phải dữ liệu lấy từ V-App — cố ý tách rời để thấy rõ ranh giới.
 */
const SEED_ROLES: Record<string, { role: UserRole; sellerId: string | null }> = {
  '11111111-1111-4111-8111-111111111111': { role: 'BUYER', sellerId: null },
  '22222222-2222-4222-8222-222222222222': {
    role: 'SELLER',
    sellerId: 'seller-a',
  },
  '33333333-3333-4333-8333-333333333333': {
    role: 'SELLER',
    sellerId: 'seller-b',
  },
};

export function findByVAppUserId(vappUserId: string): MarketUser | undefined {
  return byVAppUserId.get(vappUserId);
}

export function createUser(input: {
  vappUserId: string;
  name: string | null;
  phoneNumber: string | null;
}): MarketUser {
  const seeded = SEED_ROLES[input.vappUserId];

  const user: MarketUser = {
    id: randomUUID(),
    vappUserId: input.vappUserId,
    // Mặc định là BUYER: người dùng mới trên một sàn TMĐT là người mua.
    // Nâng lên SELLER là hành động riêng (tạo shop — ngày 3).
    role: seeded?.role ?? 'BUYER',
    sellerId: seeded?.sellerId ?? null,
    name: input.name,
    phoneNumber: input.phoneNumber,
  };

  byVAppUserId.set(user.vappUserId, user);
  return user;
}

/** Chỉ dùng trong test. */
export function resetUserStore(): void {
  byVAppUserId.clear();
}
