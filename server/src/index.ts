import { config } from './config.js';
import { buildServer } from './server.js';

const app = buildServer();

try {
  await app.listen({ port: config.port, host: config.host });
} catch (error) {
  app.log.error(error);
  process.exit(1);
}
