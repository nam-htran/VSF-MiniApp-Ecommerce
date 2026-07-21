import { StrictMode } from 'react';
import { App } from '@v-miniapp/ui-react';
import { createRoot } from 'react-dom/client';
import { getAppConfig } from './app.config';

import '@/styles/app.css';

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <App config={getAppConfig} />
  </StrictMode>
);
