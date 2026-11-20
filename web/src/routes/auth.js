import crypto from 'node:crypto';
import { Router } from 'express';
import { config } from '../config.js';
import { getSession } from '../session.js';
import { getOAuthAuthorizeUrl, exchangeCodeForToken, fetchDiscordUser } from '../discord.js';
import { requireAuth } from '../middleware/requireAuth.js';
import { requireCsrf } from '../middleware/csrf.js';
import { authLimiter } from '../middleware/limits.js';

export const authRouter = Router();

authRouter.use('/auth', authLimiter);

authRouter.get('/auth/discord', async (req, res) => {
  if (!config.oauthConfigured) {
    return res.redirect('/#setup');
  }

  const session = await getSession(req, res);
  const state = crypto.randomBytes(16).toString('hex');
  session.oauthState = state;
  session.oauthStateExpiry = Date.now() + 10 * 60 * 1000; // 10 minutes
  await session.save();

  const url = getOAuthAuthorizeUrl(state);
  res.redirect(url);
});

authRouter.get('/auth/discord/callback', async (req, res) => {
  const { code, state, error } = req.query;

  if (error) {
    return res.redirect(`/#error?message=${encodeURIComponent(String(error))}`);
  }

  if (!code || !state) {
    return res.status(400).send('Missing code or state parameter');
  }

  const session = await getSession(req, res);

  if (!session.oauthState || session.oauthState !== state || Date.now() > (session.oauthStateExpiry || 0)) {
    return res.status(403).send('Invalid or expired OAuth state');
  }

  delete session.oauthState;
  delete session.oauthStateExpiry;

  try {
    const tokens = await exchangeCodeForToken(String(code));
    const user = await fetchDiscordUser(tokens.access_token);

    if (config.allowedUserIdsSet.size > 0 && !config.allowedUserIdsSet.has(user.id)) {
      await session.save();
      return res.redirect('/#no-access');
    }

    session.user = user;
    session.csrf = crypto.randomBytes(32).toString('hex');
    await session.save();

    res.redirect('/');
  } catch (err) {
    req.log?.error(err, 'OAuth callback error');
    res.redirect(`/#error?message=${encodeURIComponent('Failed to complete Discord login')}`);
  }
});

authRouter.post('/auth/logout', requireAuth, requireCsrf, async (req, res) => {
  req.session.destroy();
  res.json({ ok: true });
});

