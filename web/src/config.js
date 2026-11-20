import dotenv from 'dotenv';
import { z } from 'zod';

dotenv.config();

const envSchema = z.object({
  HOST: z.string().default('127.0.0.1'),
  PORT: z.coerce.number().default(5000),
  PUBLIC_URL: z.string().url().refine(val => val.startsWith('http://') || val.startsWith('https://'), {
    message: 'PUBLIC_URL must start with http:// or https://'
  }),
  TRUST_PROXY: z.union([z.string(), z.number(), z.boolean()]).default('1'),
  DISCORD_CLIENT_ID: z.string().optional().default(''),
  DISCORD_CLIENT_SECRET: z.string().optional().default(''),
  SESSION_PASSWORD: z.string().min(32, 'SESSION_PASSWORD must be at least 32 characters'),
  AGENT_SECRET: z.string().min(32, 'AGENT_SECRET must be at least 32 characters'),
  ALLOWED_USER_IDS: z.string().optional().default(''),
  MAX_UPLOAD_MB: z.coerce.number().default(100),
  LOG_LEVEL: z.string().default('info')
});

const rawEnv = {
  HOST: process.env.HOST,
  PORT: process.env.PORT,
  PUBLIC_URL: (process.env.PUBLIC_URL || '').trim().replace(/\/+$/, ''),
  TRUST_PROXY: process.env.TRUST_PROXY,
  DISCORD_CLIENT_ID: (process.env.DISCORD_CLIENT_ID || '').trim(),
  DISCORD_CLIENT_SECRET: (process.env.DISCORD_CLIENT_SECRET || '').trim(),
  SESSION_PASSWORD: (process.env.SESSION_PASSWORD || '').trim(),
  AGENT_SECRET: (process.env.AGENT_SECRET || '').trim(),
  ALLOWED_USER_IDS: (process.env.ALLOWED_USER_IDS || '').trim(),
  MAX_UPLOAD_MB: process.env.MAX_UPLOAD_MB,
  LOG_LEVEL: process.env.LOG_LEVEL
};

const parsed = envSchema.safeParse(rawEnv);

if (!parsed.success) {
  console.error('Invalid environment configuration:');
  for (const issue of parsed.error.issues) {
    console.error(`  ${issue.path.join('.')}: ${issue.message}`);
  }
  process.exit(1);
}

const env = parsed.data;

const isHttps = env.PUBLIC_URL.startsWith('https://');
const oauthConfigured = Boolean(env.DISCORD_CLIENT_ID && env.DISCORD_CLIENT_SECRET);
const redirectUri = `${env.PUBLIC_URL}/auth/discord/callback`;
const agentWsUrl = env.PUBLIC_URL.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:') + '/agent';

const allowedUserIdsSet = new Set(
  env.ALLOWED_USER_IDS ? env.ALLOWED_USER_IDS.split(',').map(s => s.trim()).filter(Boolean) : []
);

export const config = {
  ...env,
  isHttps,
  oauthConfigured,
  redirectUri,
  agentWsUrl,
  allowedUserIdsSet,
  sessionOptions: {
    cookieName: 'mbui_session',
    password: env.SESSION_PASSWORD,
    ttl: 7 * 24 * 60 * 60,
    cookieOptions: {
      secure: isHttps,
      httpOnly: true,
      sameSite: 'lax',
      path: '/'
    }
  }
};

