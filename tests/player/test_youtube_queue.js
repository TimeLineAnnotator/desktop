'use strict';
// Tests for the JavaScript queue in tilia/media/player/youtube.html.
//
// Run with: node --test tests/player/test_youtube_queue.js
//
// These tests load the inline <script> from youtube.html into a sandboxed vm
// context with mocked YT / QWebChannel / DOM globals so no browser or network
// is required.
//
const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

// ---------------------------------------------------------------------------
// Script extraction
// ---------------------------------------------------------------------------

const HTML_PATH = path.resolve(__dirname, '../../tilia/media/player/youtube.html');

function extractInlineScript(htmlPath) {
  const html = fs.readFileSync(htmlPath, 'utf8');
  const match = html.match(/<script type="text\/javascript">([\s\S]*?)<\/script>/);
  if (!match) throw new Error('Could not locate inline <script type="text/javascript"> in youtube.html');
  return match[1];
}

const PLAYER_SCRIPT = extractInlineScript(HTML_PATH);

// Arrays created inside the VM sandbox belong to a different JavaScript
// "realm" and fail deepStrictEqual against host arrays even when structurally
// identical. JSON roundtrip converts them to host-realm objects.
const normalize = (v) => JSON.parse(JSON.stringify(v));

// ---------------------------------------------------------------------------
// Sandbox factory
// ---------------------------------------------------------------------------

const PLAYER_METHODS = [
  'loadPlaylist', 'seekTo', 'playVideo', 'pauseVideo', 'stopVideo',
  'setVolume', 'mute', 'unMute', 'setPlaybackRate', 'setLoop',
  'getDuration', 'getCurrentTime',
];

// Creates an isolated vm context, evaluates youtube.html's inline script
// inside it, and returns helpers for driving the player state in tests.
//
// Each test must call createSandbox() to get a fresh context; state is NOT
// shared between tests.
function createSandbox() {
  // Collects every call made to the mock player, keyed by method name.
  // calls[method] is an array of argument-lists: calls['seekTo'][0] is the
  // spread args of the first seekTo() call.
  const calls = {};

  function recordCall(method) {
    return (...args) => {
      if (!calls[method]) calls[method] = [];
      calls[method].push(args);
    };
  }

  // Minimal backend stub — the script calls backend.on_* via QWebChannel.
  const mockBackend = {
    on_player_state_change: () => {},
    on_new_time: () => {},
    on_error: () => {},
    on_set_playback_rate: () => {},
  };

  const ctx = {
    // YT.Player constructor: attach a spy for every player method so we can
    // assert what was called with what arguments later.
    YT: {
      Player: function MockPlayer(_elementId, _config) {
        for (const m of PLAYER_METHODS) this[m] = recordCall(m);
      },
      PlayerState: {
        UNSTARTED: -1, ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3, VIDEO_CUED: 5,
      },
    },

    // QWebChannel: synchronously call the callback so `backend` is wired up.
    QWebChannel: function MockWebChannel(_transport, cb) {
      cb({ objects: { backend: mockBackend } });
    },

    qt: { webChannelTransport: {} },

    // Minimal DOM: the script inserts a <script> tag at load time; we stub
    // only what is needed.
    document: {
      createElement: () => ({ id: '', src: '' }),
      getElementsByTagName: () => [{ parentNode: { insertBefore: () => {} } }],
    },

    setInterval: () => 1,
    clearInterval: () => {},
    console,
  };

  vm.createContext(ctx);
  vm.runInContext(PLAYER_SCRIPT, ctx);

  return {
    ctx,
    calls,
    // Simulates the YouTube IFrame API finishing its load and calling the
    // globally-registered onYouTubeIframeAPIReady callback.
    triggerPlayerReady: () => ctx.onYouTubeIframeAPIReady(),
    // Simulates Python calling loadVideo(id) from _engine_load_media.
    loadVideo: (id) => ctx.loadVideo(id),
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('YouTube player queue — buffering before player is ready', () => {
  test('play() before player is ready does not call player.playVideo immediately', () => {
    const { ctx, calls } = createSandbox();
    ctx.play();
    assert.equal(calls.playVideo, undefined);
  });

  test('seekTo() before player is ready does not call player.seekTo immediately', () => {
    const { ctx, calls } = createSandbox();
    ctx.seekTo(30);
    assert.equal(calls.seekTo, undefined);
  });

  test('setVolume() before player is ready does not call player.setVolume immediately', () => {
    const { ctx, calls } = createSandbox();
    ctx.setVolume(75);
    assert.equal(calls.setVolume, undefined);
  });

  test('loadVideo() before player is ready does not call player.loadPlaylist immediately', () => {
    const { ctx, calls } = createSandbox();
    ctx.loadVideo('testid1234a');
    assert.equal(calls.loadPlaylist, undefined);
  });
});

describe('YouTube player queue — argument passing (player and video both ready)', () => {
  test('seekTo passes (seconds, allowSeekAhead=true) as separate args to player.seekTo', () => {
    const { ctx, calls, triggerPlayerReady, loadVideo } = createSandbox();
    triggerPlayerReady();
    loadVideo('testid1234a');

    ctx.seekTo(30.5);

    assert.ok(calls.seekTo?.length > 0, 'player.seekTo was never called');
    assert.deepEqual(calls.seekTo[0], [30.5, true]);
  });

  test('setVolume passes the volume number as a single arg to player.setVolume', () => {
    const { ctx, calls, triggerPlayerReady, loadVideo } = createSandbox();
    triggerPlayerReady();
    loadVideo('testid1234a');

    ctx.setVolume(75);

    assert.ok(calls.setVolume?.length > 0, 'player.setVolume was never called');
    assert.deepEqual(calls.setVolume[0], [75]);
  });

  test('loadVideo passes [videoId] array as a single arg to player.loadPlaylist', () => {
    const { ctx, calls, triggerPlayerReady, loadVideo } = createSandbox();
    triggerPlayerReady();
    loadVideo('testid1234a');

    assert.ok(calls.loadPlaylist?.length > 0, 'player.loadPlaylist was never called');
    assert.deepEqual(normalize(calls.loadPlaylist[0]), [['testid1234a']]);
  });

  test('play passes no arguments to player.playVideo', () => {
    const { ctx, calls, triggerPlayerReady, loadVideo } = createSandbox();
    triggerPlayerReady();
    loadVideo('testid1234a');

    ctx.play();

    assert.ok(calls.playVideo?.length > 0, 'player.playVideo was never called');
    // Expected: player.playVideo()  →  args list = []
    // Actual (buggy): player.playVideo([[]])  →  args list = [[[]]]
    assert.deepEqual(calls.playVideo[0], []);
  });

  test('setPlaybackRate passes the rate number as a single arg', () => {
    const { ctx, calls, triggerPlayerReady, loadVideo } = createSandbox();
    triggerPlayerReady();
    loadVideo('testid1234a');

    ctx.tryPlaybackRate(1.5);

    assert.ok(calls.setPlaybackRate?.length > 0, 'player.setPlaybackRate was never called');
    // Expected: player.setPlaybackRate(1.5)  →  args list = [1.5]
    // Actual (buggy): player.setPlaybackRate([[1.5]])  →  args list = [[[1.5]]]
    assert.deepEqual(calls.setPlaybackRate[0], [1.5]);
  });
});

describe('YouTube player queue — draining queued calls with correct args', () => {
  // Calls made before the player + video are ready are held in _funcQueue.
  // _deQueue() drains them once _loadVideo() is called.
  // These tests verify that drained calls also receive the right args.

  test('seekTo queued before player ready uses correct args when drained', () => {
    const { ctx, calls, triggerPlayerReady, loadVideo } = createSandbox();

    ctx.seekTo(45.0);     // not yet ready → pushed to _funcQueue
    triggerPlayerReady(); // player created but no video → queue not drained yet
    loadVideo('testid1234a'); // video loaded → _deQueue() fires

    assert.ok(calls.seekTo?.length > 0, 'queued seekTo was never called after drain');
    assert.deepEqual(calls.seekTo[0], [45.0, true]);
  });

  test('setVolume queued before player ready uses correct arg when drained', () => {
    const { ctx, calls, triggerPlayerReady, loadVideo } = createSandbox();

    ctx.setVolume(50);
    triggerPlayerReady();
    loadVideo('testid1234a');

    assert.ok(calls.setVolume?.length > 0, 'queued setVolume was never called after drain');
    assert.deepEqual(calls.setVolume[0], [50]);
  });

  test('loadVideo before player ready triggers player.loadPlaylist with correct arg after triggerPlayerReady', () => {
    const { ctx, calls, triggerPlayerReady, loadVideo } = createSandbox();

    loadVideo('testid1234a');  // stored in videoParams, not yet called
    assert.equal(calls.loadPlaylist, undefined, 'loadPlaylist should not fire before player is ready');

    triggerPlayerReady();  // _loadPlayer() + _loadVideo(videoParams)

    assert.ok(calls.loadPlaylist?.length > 0, 'player.loadPlaylist was never called');
    assert.deepEqual(normalize(calls.loadPlaylist[0]), [['testid1234a']]);
  });

  test('multiple queued calls are all drained in order', () => {
    const { ctx, calls, triggerPlayerReady, loadVideo } = createSandbox();

    ctx.setVolume(80);
    ctx.seekTo(10.0);
    triggerPlayerReady();
    loadVideo('testid1234a');

    assert.ok(calls.setVolume?.length > 0, 'queued setVolume was not called');
    assert.ok(calls.seekTo?.length > 0, 'queued seekTo was not called');
    assert.deepEqual(calls.setVolume[0], [80]);
    assert.deepEqual(calls.seekTo[0], [10.0, true]);
  });
});
