import { Button, Image, Link, Typography } from '@v-miniapp/ui-react';
import logoVingroup from '@/assets/logo-vingroup.png';

const HomePage = () => {
  return (
    <div className="p-4 pb-[calc(var(--safe-area-inset-bottom,0px)+16px)]">
      <Image
        src={logoVingroup}
        alt="Vingroup Logo"
        width={100}
        height={100}
        fit="contain"
      />
      <Typography size="2x-large" weight={600} component="h1">
        Home Page
      </Typography>
      <Typography size="base">MiniApp UI React!</Typography>
      <Link to={'/products'}>
        <Button type="solid">Go to Products</Button>
      </Link>{' '}
    </div>
  );
};

export default HomePage;
