#!/usr/bin/env node
import crypto from 'node:crypto';
import { WebSocket } from 'ws';
import dotenv from 'dotenv';

dotenv.config();

let url = 'ws://127.0.0.1:5000/agent';
let secret = process.env.AGENT_SECRET || 'a'.repeat(32);
let exitOnReady = false;
let forgeProof = false;

const args = process.argv.slice(2);
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--url' && args[i + 1]) {
    url = args[++i];
  } else if (args[i] === '--secret' && args[i + 1]) {
    secret = args[++i];
  } else if (args[i] === '--exit-on-ready') {
    exitOnReady = true;
  } else if (args[i] === '--forge-proof') {
    forgeProof = true;
  }
}

console.log(`Connecting fake agent to ${url}...`);
const ws = new WebSocket(url);

const agentNonce = crypto.randomBytes(16).toString('hex');

ws.on('open', () => {
  console.log('WS connected. Sending hello...');
  ws.send(JSON.stringify({
    t: 'hello',
    protocol: 1,
    version: 'fake-agent-1.0',
    agentNonce
  }));
});

ws.on('message', (data) => {
  const msg = JSON.parse(data.toString('utf-8'));
  console.log('Received:', msg);

  if (msg.t === 'challenge') {
    const { serverNonce, serverProof } = msg;

    const expectedServerProof = crypto.createHmac('sha256', secret)
      .update(`server:${agentNonce}`)
      .digest('hex');

    if (serverProof !== expectedServerProof) {
      console.error('Server proof mismatch! Panel may be fraudulent or secret mismatch.');
      ws.close(4401);
      process.exit(1);
    }

    const agentProof = forgeProof
      ? crypto.randomBytes(32).toString('hex')
      : crypto.createHmac('sha256', secret)
          .update(`agent:${serverNonce}`)
          .digest('hex');

    console.log('Sending auth proof (forge=' + forgeProof + ')...');
    ws.send(JSON.stringify({
      t: 'auth',
      agentProof
    }));
  } else if (msg.t === 'ready') {
    console.log('Handshake successful! Ready.');
    if (exitOnReady) {
      ws.close(1000);
      process.exit(0);
    }
  } else if (msg.t === 'req') {
    // Basic mock response for RPC
    if (msg.action === 'bot.status') {
      ws.send(JSON.stringify({
        t: 'res',
        id: msg.id,
        ok: true,
        data: { state: 'running', version: 'fake-1.0' }
      }));
    } else if (msg.action === 'me') {
      ws.send(JSON.stringify({
        t: 'res',
        id: msg.id,
        ok: true,
        data: { isOwner: true, ownerIds: [msg.userId], guilds: [] }
      }));
    }
  }
});

ws.on('close', (code, reason) => {
  console.log(`WS closed with code ${code}: ${reason.toString()}`);
  if (code === 4401) {
    process.exit(code === 4401 ? 0 : 1);
  }
});

ws.on('error', (err) => {
  console.error('WS Error:', err.message);
  process.exit(1);
});
