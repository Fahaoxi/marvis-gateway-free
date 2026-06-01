#!/usr/bin/env node
'use strict';

const { io } = require('socket.io-client');

const CANARY_PROMPT = 'MARVIS_THIRD_PARTY_PING';
const EXPECTED_TEXT = '成功';

function parseArgs(argv) {
  const args = {
    port: 6161,
    timeoutMs: 120000,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === '--port') {
      args.port = Number.parseInt(next, 10);
      i += 1;
    } else if (arg === '--timeout-ms') {
      args.timeoutMs = Number.parseInt(next, 10);
      i += 1;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return args;
}

function runCanary(args) {
  const socket = io(`http://127.0.0.1:${args.port}/agent`, {
    transports: ['polling'],
    timeout: 20000,
    reconnection: false,
  });
  const state = {
    conversationId: null,
    text: '',
  };
  let finished = false;
  let timeout = null;

  function finish(code, reason) {
    if (finished) return;
    finished = true;
    if (timeout) clearTimeout(timeout);
    console.log('SUMMARY', JSON.stringify({
      ok: code === 0,
      reason,
      conversationId: state.conversationId,
      prompt: CANARY_PROMPT,
      expectedText: EXPECTED_TEXT,
      actualText: state.text,
    }, null, 2));
    try {
      socket.close();
    } catch {
      // Ignore close errors during process exit.
    }
    setTimeout(() => process.exit(code), 100);
  }

  socket.on('connect', () => {
    socket.emit('agent.action', {
      action: 'conversations.create',
      title: 'third-party adapter canary',
    }, (ack) => {
      state.conversationId = ack?.data?.id;
      if (!state.conversationId) {
        finish(2, 'no conversation id');
        return;
      }
      socket.emit('agent.run', {
        conversation_id: state.conversationId,
        message: CANARY_PROMPT,
        attachments: [],
      }, () => {});
    });
  });

  socket.on('ag_ui_event', (event) => {
    if (event?.type === 'TEXT_MESSAGE_CONTENT') {
      state.text += event.delta || '';
    }
    if (event?.type === 'RUN_ERROR') {
      finish(3, 'run error');
      return;
    }
    if (event?.type === 'TEXT_MESSAGE_END' || event?.type === 'RUN_FINISHED') {
      finish(state.text.includes(EXPECTED_TEXT) ? 0 : 4, 'completed');
    }
  });

  socket.on('connect_error', (err) => {
    finish(5, err?.message || 'connect error');
  });

  timeout = setTimeout(() => {
    finish(6, 'timeout');
  }, args.timeoutMs);
}

try {
  runCanary(parseArgs(process.argv.slice(2)));
} catch (err) {
  console.error(err?.message || String(err));
  process.exit(1);
}

