import { StrictMode } from 'react';
import { App } from '@v-miniapp/ui-react';
import { createRoot } from 'react-dom/client';
import { getAppConfig } from './app.config';

// Teaches the transport how to get a fresh token when one expires.
// Imported for the side effect, before any screen can make a call.
import '@/lib/session-renew';
import '@/styles/app.css';

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <App config={getAppConfig} />
  </StrictMode>
);
