import Fastify from 'fastify';
import type { FastifyInstance } from 'fastify';
import { config, isMock } from './config.js';
import { registerMockVAppRoutes } from './vapp/mock/routes.js';
import { registerAuthRoutes } from './auth/routes.js';

/**
 * Dựng server. Tách khỏi index.ts để test có thể build app riêng,
 * chạy trên cổng tạm rồi tắt.
 */
export function buildServer(): FastifyInstance {
  const app = Fastify({
    logger: config.nodeEnv !== 'test',
  });

  app.get('/healthz', async () => ({
    status: 'ok',
    vappMode: config.vapp.mode,
  }));

  registerAuthRoutes(app);

  // Bản mô phỏng V-App chỉ tồn tại ở chế độ mock. Ở chế độ real,
  // /__vapp không được đăng ký — gọi vào sẽ 404, đúng như mong đợi.
  if (isMock) {
    registerMockVAppRoutes(app);
    app.log.warn(
      'VAPP_MODE=mock — bản mô phỏng V-App đang bật tại /__vapp. ' +
        'Không dùng cấu hình này ngoài môi trường phát triển.'
    );
  }

  return app;
}
