import { Typography } from '@v-miniapp/ui-react';

const AboutPage = () => {
  return (
    <div className="p-4">
      <Typography size="2x-large" weight={600} component="h1">
        About MiniApp
      </Typography>
      <Typography size="base">This is MiniApp example</Typography>
    </div>
  );
};

export default AboutPage;
