import crypto from 'node:crypto';
import { getIronSession, unsealData, sealData } from 'iron-session';
import { config } from './config.js';

export async function getSession(req, res) {
  const session = await getIronSession(req, res, config.sessionOptions);
  if (!session.csrf) {
    session.csrf = crypto.randomBytes(32).toString('hex');
    await session.save();
  }
  return session;
}

export async function getSessionFromCookieHeader(cookieHeader) {
  if (!cookieHeader) return null;
  const cookieName = config.sessionOptions.cookieName;
  const match = cookieHeader.match(new RegExp(`(?:^|;\\s*)${cookieName}=([^;]+)`));
  if (!match) return null;
  const sealed = decodeURIComponent(match[1]);
  try {
    const data = await unsealData(sealed, {
      password: config.SESSION_PASSWORD,
      ttl: config.sessionOptions.ttl
    });
    return data;
  } catch (err) {
    return null;
  }
}

export async function createSealedSession(userData) {
  const sessionData = {
    user: userData,
    csrf: crypto.randomBytes(32).toString('hex')
  };
  return sealData(sessionData, {
    password: config.SESSION_PASSWORD,
    ttl: config.sessionOptions.ttl
  });
}

