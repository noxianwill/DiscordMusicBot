#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';
import dotenv from 'dotenv';
import { sealData } from 'iron-session';

dotenv.config();

const args = process.argv.slice(2);
if (!args.includes('--local')) {
  console.error('Error: selftest must be run with --local flag.');
  process.exit(1);
}

const targetHost = process.env.HOST || '127.0.0.1';
if (targetHost !== '127.0.0.1' && targetHost !== 'localhost') {
  console.error(`Error: selftest only runs against 127.0.0.1/localhost, got: ${targetHost}`);
  process.exit(1);
}

const port = process.env.PORT || 5000;
const baseUrl = `http://127.0.0.1:${port}`;
const sessionPassword = process.env.SESSION_PASSWORD;

if (!sessionPassword || sessionPassword.length < 32) {
  console.error('Error: Valid SESSION_PASSWORD (>= 32 chars) required in .env');
  process.exit(1);
}

// Find owner Discord ID
let ownerId = null;
const botDir = process.env.BOT_DIR || path.resolve(process.cwd(), '..');
const ownerArgIdx = args.indexOf('--owner');
if (ownerArgIdx !== -1 && args[ownerArgIdx + 1]) {
  ownerId = args[ownerArgIdx + 1].trim();
} else {
  // Try reading from data/panel_state.json
  const panelStatePath = path.join(botDir, 'data', 'panel_state.json');
  if (fs.existsSync(panelStatePath)) {
    try {
      const data = JSON.parse(fs.readFileSync(panelStatePath, 'utf-8'));
      if (data.ownerIds && data.ownerIds.length > 0) {
        ownerId = String(data.ownerIds[0]);
      }
    } catch (_) {}
  }
}

if (!ownerId) {
  // Try reading config.txt for PANEL_OWNER_IDS
  const configPath = path.join(botDir, 'config.txt');
  if (fs.existsSync(configPath)) {
    const content = fs.readFileSync(configPath, 'utf-8');
    const match = content.match(/^PANEL_OWNER_IDS=([0-9,]+)/m);
    if (match) {
      ownerId = match[1].split(',')[0].trim();
    }
  }
}

if (!ownerId) {
  ownerId = '999999999999999999';
}

console.log(`Starting selftest against ${baseUrl} using owner ID ${ownerId}...`);

async function createCookie(userId, csrfToken = 'test-csrf-token') {
  const sessionData = {
    user: {
      id: String(userId),
      username: `testuser_${userId}`,
      globalName: `Test User ${userId}`,
      avatar: null,
      avatarUrl: `https://cdn.discordapp.com/embed/avatars/0.png`
    },
    csrf: csrfToken
  };

  const sealed = await sealData(sessionData, {
    password: sessionPassword,
    ttl: 3600
  });

  return {
    cookieHeader: `mbui_session=${encodeURIComponent(sealed)}`,
    csrf: csrfToken
  };
}

async function runStep(stepName, fn) {
  try {
    process.stdout.write(`- ${stepName} ... `);
    const res = await fn();
    console.log('PASS');
    return res;
  } catch (err) {
    console.log(`FAIL (${err.message})`);
    throw err;
  }
}

async function requestJson(urlPath, options = {}, auth) {
  const headers = { ...(options.headers || {}) };
  if (auth) {
    headers['Cookie'] = auth.cookieHeader;
    if (auth.csrf && options.method && options.method !== 'GET') {
      headers['X-CSRF-Token'] = auth.csrf;
    }
  }

  const res = await fetch(`${baseUrl}${urlPath}`, {
    ...options,
    headers
  });

  const contentType = res.headers.get('content-type') || '';
  let body;
  if (contentType.includes('application/json')) {
    body = await res.json();
  } else {
    body = await res.text();
  }

  return { status: res.status, ok: res.ok, body };
}

async function main() {
  const ownerAuth = await createCookie(ownerId, 'owner-csrf-token');
  const randomNonOwnerAuth = await createCookie('111222333444555666', 'nonowner-csrf-token');

  // Step 1: /api/me -> isOwner true
  await runStep('1. /api/me returns isOwner=true', async () => {
    const res = await requestJson('/api/me', { method: 'GET' }, ownerAuth);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${JSON.stringify(res.body)}`);
    if (!res.body.bot) throw new Error('bot data is null');
    if (!res.body.bot.isOwner) throw new Error(`isOwner is false for ownerId=${ownerId}`);
  });

  // Step 2: bot.status running
  await runStep('2. bot.status reports running', async () => {
    const res = await requestJson('/api/rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'bot.status' })
    }, ownerAuth);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${JSON.stringify(res.body)}`);
    if (res.body.data?.state !== 'running') {
      throw new Error(`Expected state 'running', got '${res.body.data?.state}'`);
    }
  });

  // Step 3: playlists.create selftest
  await runStep('3. playlists.create selftest', async () => {
    const res = await requestJson('/api/rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'playlists.create',
        params: { name: 'selftest' }
      })
    }, ownerAuth);
    if (!res.ok && !res.body.error?.includes('already exists')) {
      throw new Error(`HTTP ${res.status}: ${JSON.stringify(res.body)}`);
    }
  });

  // Step 4: generate mp3 and upload
  const testMp3 = '/tmp/selftest.mp3';
  if (!fs.existsSync(testMp3)) {
    execSync('ffmpeg -y -f lavfi -i sine=frequency=440:duration=5 -q:a 9 /tmp/selftest.mp3 2>/dev/null');
  }
  const mp3Buffer = fs.readFileSync(testMp3);

  await runStep('4. upload 5s sine mp3 to selftest playlist', async () => {
    const res = await fetch(`${baseUrl}/api/upload?playlist=selftest&filename=selftest.mp3&overwrite=true`, {
      method: 'POST',
      headers: {
        'Cookie': ownerAuth.cookieHeader,
        'X-CSRF-Token': ownerAuth.csrf,
        'Content-Type': 'application/octet-stream',
        'Content-Length': String(mp3Buffer.length)
      },
      body: mp3Buffer
    });
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`Upload failed: ${res.status} ${txt}`);
    }
    const data = await res.json();
    if (!data.ok) throw new Error(`Upload response error: ${JSON.stringify(data)}`);
  });

  // Step 5: playlists.get selftest contains file
  await runStep('5. playlists.get selftest contains selftest.mp3', async () => {
    const res = await requestJson('/api/rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'playlists.get',
        params: { name: 'selftest' }
      })
    }, ownerAuth);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${JSON.stringify(res.body)}`);
    const tracks = res.body.data?.tracks || [];
    if (!tracks.some(t => t.file === 'selftest.mp3')) {
      throw new Error(`Track selftest.mp3 not found in tracks: ${JSON.stringify(tracks)}`);
    }
  });

  // Step 6: tracks.delete
  await runStep('6. tracks.delete removes selftest.mp3', async () => {
    const res = await requestJson('/api/rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'tracks.delete',
        params: { playlist: 'selftest', file: 'selftest.mp3' }
      })
    }, ownerAuth);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${JSON.stringify(res.body)}`);
  });

  // Step 7: playlists.delete selftest
  await runStep('7. playlists.delete removes selftest playlist', async () => {
    const res = await requestJson('/api/rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'playlists.delete',
        params: { name: 'selftest' }
      })
    }, ownerAuth);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${JSON.stringify(res.body)}`);
  });

  // Step 8: cookies.status has no raw values
  await runStep('8. cookies.status exposes no raw cookie values', async () => {
    const res = await requestJson('/api/rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'cookies.status' })
    }, ownerAuth);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${JSON.stringify(res.body)}`);
    const str = JSON.stringify(res.body);
    if (str.includes('content') || str.includes('value') || str.includes('token')) {
      throw new Error(`Possible cookie leak detected in: ${str}`);
    }
  });

  // Step 9: settings.get has no secrets
  await runStep('9. settings.get exposes no secrets', async () => {
    const res = await requestJson('/api/rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'settings.get' })
    }, ownerAuth);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${JSON.stringify(res.body)}`);
    const keys = Object.keys(res.body.data || {});
    for (const k of keys) {
      if (['TOKEN', 'SECRET', 'PASSWORD'].some(s => k.toUpperCase().includes(s))) {
        throw new Error(`Secret key leaked: ${k}`);
      }
    }
  });

  // Step 10: non-owner gets 403 on bot.restart
  await runStep('10. Non-owner gets 403 on bot.restart', async () => {
    const res = await requestJson('/api/rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'bot.restart' })
    }, randomNonOwnerAuth);
    if (res.status !== 403) {
      throw new Error(`Expected HTTP 403, got ${res.status}: ${JSON.stringify(res.body)}`);
    }
  });

  // Step 11: bot.restart returns to running within 60s
  await runStep('11. Owner bot.restart returns to running within 60s', async () => {
    const res = await requestJson('/api/rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'bot.restart' })
    }, ownerAuth);
    if (!res.ok) throw new Error(`Restart call failed: HTTP ${res.status}: ${JSON.stringify(res.body)}`);

    // Poll status until running (up to 60s as per IMPLEMENTATION_PLAN §7.4 / §10 check 8)
    const startPoll = Date.now();
    let backToRunning = false;
    while (Date.now() - startPoll < 60000) {
      await new Promise(r => setTimeout(r, 1000));
      try {
        const checkRes = await requestJson('/api/rpc', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'bot.status' })
        }, ownerAuth);
        if (checkRes.ok && checkRes.body.data?.state === 'running') {
          backToRunning = true;
          break;
        }
      } catch (_) {}
    }
    if (!backToRunning) {
      throw new Error('Bot did not return to running state within 60 seconds');
    }
  });

  console.log('\nAll selftest steps completed successfully!');
}

main().catch(() => {
  process.exit(1);
});

