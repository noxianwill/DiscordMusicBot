export function requireCsrf(req, res, next) {
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) {
    return next();
  }

  const token = req.headers['x-csrf-token'];
  const sessionToken = req.session?.csrf;

  if (!token || !sessionToken || token !== sessionToken) {
    return res.status(403).json({
      ok: false,
      code: 'FORBIDDEN',
      error: 'Invalid or missing CSRF token'
    });
  }

  next();
}

