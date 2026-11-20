import rateLimit from 'express-rate-limit';

export const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 20,
  standardHeaders: true,
  legacyHeaders: false,
  message: { ok: false, code: 'TOO_MANY_REQUESTS', error: 'Too many authentication requests, try again later' }
});

export const rpcLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 120,
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator: (req) => req.session?.user?.id || req.ip,
  message: { ok: false, code: 'TOO_MANY_REQUESTS', error: 'Too many RPC requests, please slow down' }
});

export const uploadLimiter = rateLimit({
  windowMs: 60 * 60 * 1000,
  max: 30,
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator: (req) => req.session?.user?.id || req.ip,
  message: { ok: false, code: 'TOO_MANY_REQUESTS', error: 'Upload rate limit exceeded' }
});

