import { OptionItem, SearchField } from '@v-miniapp/ui-react';

const ProductsPage = () => {
  return (
    <div className="flex flex-col">
      <div className="p-4">
        <SearchField placeholder="Tìm kiếm..." />
      </div>
      <div className="flex-1 overflow-x-hidden overflow-y-auto p-4 pb-[calc(var(--safe-area-inset-bottom,0px)+16px)]">
        <div className="flex flex-col gap-4">
          {Array(10)
            .fill(0)
            .map((_, index) => (
              <OptionItem key={index} title="Sản phẩm">
                Sản phẩm #{index + 1}
              </OptionItem>
            ))}
        </div>
      </div>
    </div>
  );
};

export default ProductsPage;
