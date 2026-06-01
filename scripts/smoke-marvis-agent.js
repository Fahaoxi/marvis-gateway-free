#!/usr/bin/env node
'use strict';

const { io } = require('socket.io-client');

const DEFAULT_PORT = 6161;
const DEFAULT_TIMEOUT_MS = 180000;

function parseArgs(argv) {
  const args = {
    mode: 'simple',
    port: DEFAULT_PORT,
    url: null,
    timeoutMs: DEFAULT_TIMEOUT_MS,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];

    if (arg === '--help' || arg === '-h') {
      args.help = true;
    } else if (arg === '--mode') {
      args.mode = next;
      i += 1;
    } else if (arg === '--port') {
      args.port = Number.parseInt(next, 10);
      i += 1;
    } else if (arg === '--url') {
      args.url = next;
      i += 1;
    } else if (arg === '--timeout-ms') {
      args.timeoutMs = Number.parseInt(next, 10);
      i += 1;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!['simple', 'tool'].includes(args.mode)) {
    throw new Error('--mode must be simple or tool');
  }
  if (!Number.isInteger(args.port) || args.port <= 0 || args.port > 65535) {
    throw new Error('--port must be an integer between 1 and 65535');
  }
  if (!Number.isInteger(args.timeoutMs) || args.timeoutMs < 1000) {
    throw new Error('--timeout-ms must be an integer >= 1000');
  }

  return args;
}

function printHelp() {
  console.log(`Usage:
  node scripts/smoke-marvis-agent.js --port 6161 --mode simple
  node scripts/smoke-marvis-agent.js --port 6161 --mode tool
  node scripts/smoke-marvis-agent.js --url http://127.0.0.1:6161/agent --mode simple

Options:
  --mode simple|tool      Smoke mode. simple asks "只回复 ok"; tool waits for RUN_FINISHED.
  --port <number>         Agent port used to build http://127.0.0.1:<port>/agent.
  --url <url>             Full Socket.IO URL. Overrides --port.
  --timeout-ms <number>   Timeout in milliseconds. Default: ${DEFAULT_TIMEOUT_MS}.
`);
}

function extractConversationId(ack) {
  return ack?.data?.data?.id || ack?.data?.id || ack?.id || null;
}

function flatten(items) {
  const out = [];
  for (const item of items) {
    if (Array.isArray(item)) {
      out.push(...flatten(item));
    } else {
      out.push(item);
    }
  }
  return out;
}

function summarizeEventArgs(args, state) {
  const flatArgs = flatten(args);
  const payload = JSON.stringify(args);

  state.eventCount += 1;

  const toolHints = [
    'TOOL',
    'tool',
    'FUNCTION',
    'function',
    'MCP',
    'mcp',
    'dispatch_task',
    'system_info',
    'shell_executor',
  ];

  if (toolHints.some((hint) => payload.includes(hint))) {
    state.sawToolSignal = true;
  }

  for (const arg of flatArgs) {
    if (!arg || typeof arg !== 'object') continue;

    if (arg.type === 'TEXT_MESSAGE_CONTENT' && typeof arg.delta === 'string') {
      state.text += arg.delta;
      state.sawTextContent = true;
    }
    if (arg.type === 'TEXT_MESSAGE_END') {
      state.sawTextEnd = true;
    }
    if (arg.type === 'RUN_FINISHED') {
      state.sawRunFinished = true;
    }
    if (arg.type === 'RUN_ERROR') {
      state.sawRunError = true;
    }
  }

  return payload;
}

function makeSummary(reason, state) {
  return {
    reason,
    mode: state.mode,
    url: state.url,
    connected: state.connected,
    conversationId: state.conversationId,
    sawTextContent: state.sawTextContent,
    sawTextEnd: state.sawTextEnd,
    sawRunFinished: state.sawRunFinished,
    sawRunError: state.sawRunError,
    sawToolSignal: state.sawToolSignal,
    eventCount: state.eventCount,
    text: state.text.slice(0, 500),
    createAckOk: Boolean(state.createAck),
    runAckOk: Boolean(state.runAck),
  };
}

function runSmoke(args) {
  const url = args.url || `http://127.0.0.1:${args.port}/agent`;
  const state = {
    mode: args.mode,
    url,
    connected: false,
    conversationId: null,
    createAck: null,
    runAck: null,
    text: '',
    sawTextContent: false,
    sawTextEnd: false,
    sawRunFinished: false,
    sawRunError: false,
    sawToolSignal: false,
    eventCount: 0,
  };

  const socket = io(url, {
    transports: ['polling'],
    timeout: 20000,
    reconnection: false,
  });

  let finished = false;
  let timeout = null;

  function finish(code, reason) {
    if (finished) return;
    finished = true;
    if (timeout) clearTimeout(timeout);

    const summary = makeSummary(reason, state);
    console.log('SUMMARY', JSON.stringify(summary, null, 2));

    try {
      socket.close();
    } catch {
      // Ignore close errors while exiting the probe.
    }

    setTimeout(() => process.exit(code), 100);
  }

  function shouldFinishSuccessfully() {
    if (args.mode === 'simple') {
      return state.sawTextContent || state.sawTextEnd || state.sawRunFinished;
    }
    return state.sawRunFinished;
  }

  socket.on('connect', () => {
    state.connected = true;
    console.log('CONNECT', socket.id);

    socket.emit('agent.action', {
      action: 'conversations.create',
      title: `marvis ${args.mode} smoke`,
    }, (ack) => {
      state.createAck = ack;
      console.log('CREATE_ACK', JSON.stringify(ack));

      const conversationId = extractConversationId(ack);
      if (!conversationId) {
        finish(2, 'no conversation id');
        return;
      }

      state.conversationId = conversationId;
      const message = args.mode === 'simple'
        ? '只回复 ok'
        : '请使用可用工具查看这台电脑的系统信息或当前用户名，然后用一句中文概括结果。不要猜测。';

      socket.emit('agent.run', {
        conversation_id: conversationId,
        message,
        attachments: [],
      }, (runAck) => {
        state.runAck = runAck;
        console.log('RUN_ACK', JSON.stringify(runAck));
      });
    });
  });

  socket.on('connect_error', (err) => {
    console.log('CONNECT_ERROR', err?.message || String(err));
    finish(6, 'connect error');
  });

  for (const evt of ['ag_ui_event', 'agent.run', 'agent.action', 'gateway.connected', 'gateway.tick', 'error']) {
    socket.on(evt, (...eventArgs) => {
      const payload = summarizeEventArgs(eventArgs, state);
      console.log('EVENT', evt, payload);

      if (state.sawRunError) {
        finish(3, 'run error');
        return;
      }

      if (shouldFinishSuccessfully()) {
        finish(0, args.mode === 'tool' ? 'run finished' : 'assistant text observed');
      }
    });
  }

  timeout = setTimeout(() => {
    const code = state.conversationId && state.runAck ? 4 : 5;
    finish(code, 'timeout');
  }, args.timeoutMs);
}

try {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    printHelp();
    process.exit(0);
  }
  runSmoke(args);
} catch (err) {
  console.error(err?.message || String(err));
  printHelp();
  process.exit(1);
}
