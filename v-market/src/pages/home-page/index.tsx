import { FlashSaleSection } from '@/components/flash-sale-section';
import { ProductGridSection } from '@/components/product-grid-section';
import { PromoSection } from '@/components/promo-section';

/**
 * Being assembled block by block against the reference design. The shop
 * data fetch comes back with the next block that actually lists shops —
 * a request nothing renders is a request the page should not make.
 */
const HomePage = () => (
  <div className="flex flex-col">
    <PromoSection />
    <FlashSaleSection />
    <ProductGridSection />
  </div>
);

export default HomePage;
