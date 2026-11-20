import { getSession } from '../session.js';

export async function requireAuth(req, res, next) {
  try {
    const session = await getSession(req, res);
    if (!session.user || !session.user.id) {
      return res.status(401).json({
        ok: false,
        code: 'UNAUTHORIZED',
        error: 'Authentication required'
      });
    }
    req.session = session;
    req.user = session.user;
    next();
  } catch (err) {
    next(err);
  }
}

