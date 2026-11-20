import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';
import helmet from 'helmet';
import pino from 'pino';
import pinoHttp from 'pino-http';
import { config } from './config.js';
import { healthRouter } from './routes/health.js';
import { authRouter } from './routes/auth.js';
import { apiRouter } from './routes/api.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const publicDir = path.resolve(__dirname, '../public');

export const app = express();

app.set('trust proxy', config.TRUST_PROXY);

const logger = pino({
  level: config.LOG_LEVEL,
  redact: {
    paths: [
      'req.headers.cookie',
      'req.headers.authorization',
      'req.body.params.text',
      'req.body.params.values'
    ],
    remove: true
  }
});

app.use(pinoHttp({
  logger,
  customLogLevel: (req, res, err) => {
    if (res.statusCode >= 500 || err) return 'error';
    if (res.statusCode >= 400) return 'warn';
    return 'info';
  }
}));

app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      imgSrc: ["'self'", "data:", "https://cdn.discordapp.com", "https://i.ytimg.com", "https://*.ytimg.com"],
      connectSrc: ["'self'", "wss:", "ws:"],
      frameAncestors: ["'none'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"]
    }
  }
}));

app.use(express.json({ limit: '512kb' }));

// Static files
app.use(express.static(publicDir));

// Routes
app.use(healthRouter);
app.use(authRouter);
app.use(apiRouter);

// Fallback to index.html for frontend routing
app.get('{*path}', (req, res, next) => {
  if (req.path.startsWith('/api') || req.path.startsWith('/auth')) {
    return next();
  }
  res.sendFile(path.join(publicDir, 'index.html'));
});

// Centralized error handler
app.use((err, req, res, next) => {
  req.log?.error(err, 'Unhandled request error');
  if (res.headersSent) {
    return next(err);
  }
  const status = err.status || err.statusCode || 500;
  res.status(status).json({
    ok: false,
    code: err.code || 'INTERNAL_ERROR',
    error: status === 500 ? 'Internal Server Error' : err.message
  });
});
