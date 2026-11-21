import fs from 'node:fs';
import path from 'node:path';
import { Router } from 'express';
import { z } from 'zod';
import { config } from '../config.js';
import { getSession } from '../session.js';
import { requireAuth } from '../middleware/requireAuth.js';
import { requireCsrf } from '../middleware/csrf.js';
import { rpcLimiter, uploadLimiter } from '../middleware/limits.js';
import { isAgentConnected, getAgentSocket, requestAgent } from '../agent/connection.js';
import { streamUploadToAgent } from '../agent/uploads.js';

export const apiRouter = Router();

const ALLOWED_RPC_ACTIONS = new Set([
  'bot.status', 'bot.start', 'bot.stop', 'bot.restart',
  'logs.tail', 'cookies.status', 'cookies.get', 'cookies.set',
  'settings.get', 'settings.set',
  'playlists.create', 'playlists.rename', 'playlists.delete', 'tracks.delete',
  'playlists.import_youtube', 'playlists.inspect_youtube',
  'me', 'guild.state', 'guild.channels', 'join', 'leave',
  'play', 'play.local',
  'pause', 'resume', 'stop', 'skip', 'previous', 'restart', 'seek', 'volume', 'loop',
  'queue.get', 'queue.play', 'queue.remove', 'queue.move', 'queue.clear', 'queue.shuffle',
  'history', 'playlists.list', 'playlists.get', 'playlists.reload', 'lyrics.get', 'voice.optimize'
]);

const rpcSchema = z.object({
  action: z.string().refine(val => ALLOWED_RPC_ACTIONS.has(val), {
    message: 'Action not allowed'
  }),
  guildId: z.union([z.string(), z.number()]).optional().nullable(),
  params: z.record(z.any()).optional().default({})
});

// GET /api/status - Public
apiRouter.get('/api/status', (req, res) => {
  res.json({
    oauthConfigured: config.oauthConfigured,
    agentConnected: isAgentConnected(),
    redirectUri: config.redirectUri,
    agentWsUrl: config.agentWsUrl
  });
});

// GET /api/public/live - Public read-only live player and queue for guest listener link
apiRouter.get('/api/public/live', async (req, res) => {
  const guildId = req.query.guildId;
  if (!guildId || !/^\d{17,20}$/.test(String(guildId))) {
    return res.status(400).json({ error: 'Valid guildId query parameter is required' });
  }

  if (!isAgentConnected()) {
    return res.status(503).json({ error: 'Bot agent is currently offline' });
  }

  try {
    const [stateRes, queueRes] = await Promise.all([
      requestAgent('guild.state', '0', String(guildId), {}).catch(() => null),
      requestAgent('queue.get', '0', String(guildId), {}).catch(() => null)
    ]);

    res.json({
      ok: true,
      data: {
        guildId: String(guildId),
        state: stateRes,
        queue: queueRes
      }
    });
  } catch (err) {
    res.status(500).json({ error: err.message || 'Failed to fetch live state' });
  }
});

// GET /api/me - Authenticated
apiRouter.get('/api/me', requireAuth, async (req, res) => {
  const agentConnected = isAgentConnected();
  let botData = null;
  let botStatus = null;

  if (agentConnected) {
    try {
      botStatus = await requestAgent('bot.status', req.user.id, null, {});
    } catch (_) {}

    try {
      botData = await requestAgent('me', req.user.id, null, {});
    } catch (_) {}
  }

  const isOwner = Boolean(botData?.isOwner);
  const guilds = botData?.guilds || [];
  const innerBot = botData?.bot || {};

  const botInfo = {
    ...innerBot,
    state: botStatus?.state || (agentConnected ? 'running' : 'stopped'),
    status: botStatus,
    isOwner,
    guilds
  };

  res.json({
    user: req.user,
    isOwner,
    guilds,
    bot: botInfo,
    botStatus,
    agentConnected,
    csrfToken: req.session.csrf
  });
});

// POST /api/rpc - Authenticated, CSRF protected, rate limited
apiRouter.post('/api/rpc', requireAuth, requireCsrf, rpcLimiter, async (req, res) => {
  const parsed = rpcSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({
      ok: false,
      code: 'BAD_REQUEST',
      error: parsed.error.issues.map(i => i.message).join(', ')
    });
  }

  if (!isAgentConnected()) {
    return res.status(503).json({
      ok: false,
      code: 'BOT_OFFLINE',
      error: 'Bot agent is not connected'
    });
  }

  const { action, guildId, params } = parsed.data;

  try {
    if (action === 'settings.get') {
      const result = await requestAgent(action, req.user.id, guildId ? String(guildId) : null, params);
      const data = { ...(result || {}) };
      data.ALLOWED_USER_IDS = Array.from(config.allowedUserIdsSet || []).join(',');
      data.MAX_UPLOAD_MB = String(config.MAX_UPLOAD_MB || 100);
      data.TRUST_PROXY = String(config.TRUST_PROXY || 1);
      data.PUBLIC_URL = String(config.PUBLIC_URL || '');
      return res.json({ ok: true, data });
    }

    if (action === 'settings.set') {
      const vals = { ...(params.values || {}) };
      const envKeys = ['ALLOWED_USER_IDS', 'MAX_UPLOAD_MB', 'TRUST_PROXY', 'PUBLIC_URL'];
      const envUpdates = {};
      for (const k of envKeys) {
        if (k in vals) {
          envUpdates[k] = String(vals[k]).trim();
          delete vals[k];
        }
      }
      if (Object.keys(envUpdates).length > 0) {
        try {
          const envPath = path.resolve(process.cwd(), '.env');
          let envContent = fs.readFileSync(envPath, 'utf-8');
          for (const [k, v] of Object.entries(envUpdates)) {
            const regex = new RegExp(`^${k}=.*$`, 'm');
            if (regex.test(envContent)) {
              envContent = envContent.replace(regex, `${k}=${v}`);
            } else {
              envContent += `\n${k}=${v}\n`;
            }
            if (k === 'MAX_UPLOAD_MB') config.MAX_UPLOAD_MB = Number(v) || 100;
            if (k === 'TRUST_PROXY') config.TRUST_PROXY = v;
            if (k === 'PUBLIC_URL') config.PUBLIC_URL = v;
            if (k === 'ALLOWED_USER_IDS') {
              config.allowedUserIdsSet = new Set(v.split(',').map(s => s.trim()).filter(Boolean));
            }
          }
          fs.writeFileSync(envPath, envContent, { mode: 0o600 });
        } catch (e) {
          req.log?.error(e, 'Error updating .env file');
        }
      }
      const result = await requestAgent(action, req.user.id, guildId ? String(guildId) : null, { values: vals });
      return res.json({ ok: true, data: result });
    }

    const result = await requestAgent(action, req.user.id, guildId ? String(guildId) : null, params);
    res.json({ ok: true, data: result });
  } catch (err) {
    const code = err.code || 'INTERNAL';
    let httpStatus = 500;
    if (code === 'FORBIDDEN') httpStatus = 403;
    else if (code === 'BOT_OFFLINE') httpStatus = 503;
    else if (code === 'NOT_FOUND') httpStatus = 404;
    else if (code === 'BAD_REQUEST' || code === 'NOT_IN_VOICE') httpStatus = 400;
    else if (code === 'TIMEOUT') httpStatus = 504;

    res.status(httpStatus).json({
      ok: false,
      code,
      error: err.message || 'Operation failed'
    });
  }
});

// POST /api/upload - Authenticated, CSRF protected, rate limited
apiRouter.post('/api/upload', requireAuth, requireCsrf, uploadLimiter, async (req, res) => {
  if (!isAgentConnected()) {
    return res.status(503).json({
      ok: false,
      code: 'BOT_OFFLINE',
      error: 'Bot agent is not connected'
    });
  }

  const playlist = String(req.query.playlist || '').trim();
  const filename = String(req.query.filename || '').trim();
  const overwrite = req.query.overwrite === 'true' || req.query.overwrite === '1';

  if (!playlist || !filename) {
    return res.status(400).json({
      ok: false,
      code: 'BAD_REQUEST',
      error: 'Missing playlist or filename query parameter'
    });
  }

  const contentLength = Number(req.headers['content-length']);
  const maxBytes = config.MAX_UPLOAD_MB * 1024 * 1024;
  if (!contentLength || isNaN(contentLength)) {
    return res.status(400).json({
      ok: false,
      code: 'BAD_REQUEST',
      error: 'Missing or invalid Content-Length header'
    });
  }
  if (contentLength > maxBytes) {
    return res.status(400).json({
      ok: false,
      code: 'BAD_REQUEST',
      error: `File size exceeds maximum allowed ${config.MAX_UPLOAD_MB} MB`
    });
  }

  try {
    const agentWs = getAgentSocket();
    const result = await streamUploadToAgent(agentWs, req, playlist, filename, overwrite);
    res.json({ ok: true, data: result });
  } catch (err) {
    const code = err.code || 'INTERNAL';
    let httpStatus = 500;
    if (code === 'FORBIDDEN') httpStatus = 403;
    else if (code === 'NOT_FOUND') httpStatus = 404;
    else if (code === 'BAD_REQUEST') httpStatus = 400;
    else if (code === 'TIMEOUT') httpStatus = 504;

    res.status(httpStatus).json({
      ok: false,
      code,
      error: err.message || 'Upload failed'
    });
  }
});

