/* JARVIS voice — browser-side speech interface.
 *
 * Wires the Orbit chat to the bridge voice endpoints:
 *
 *   push-to-talk mic  →  MediaRecorder  →  POST /v1/stt  →  chat text
 *   assistant reply   →  POST /v1/tts   →  Audio() playback (hands-free mode)
 *
 * Engines are chosen server-side (/v1/voice/status): ElevenLabs neural voices
 * when ELEVENLABS_API_KEY is configured, Windows SAPI narration otherwise —
 * so speaking works with zero setup. The API key never reaches this file.
 *
 * Mark-LIV behaviors folded in:
 *   - push-to-talk (hold) AND hands-free auto-listen after speaking
 *   - instant acknowledgment spoken before long tasks start
 *   - self-echo guard: mic ignores while JARVIS audio is playing
 *   - hybrid input: voice and keyboard compose in the same composer
 */
(function () {
  'use strict';

  var _bridge = (window.dshNative && window.dshNative.config && window.dshNative.config.baseUrl) || 'http://127.0.0.1:8170';
  function _bearer() {
    // Same per-launch token dsh-native uses (preload boundary → main).
    try {
      if (window.dshNative && window.dshNative.config && window.dshNative.config.authToken) {
        return window.dshNative.config.authToken;
      }
      if (window.orbit && typeof window.orbit.getBridgeToken === 'function') {
        return window.orbit.getBridgeToken();
      }
    } catch (e) {}
    return null;
  }
  var _token = _bearer();

  function headers(extra) {
    var h = { 'Content-Type': 'application/json' };
    var tok = _token || _bearer();
    if (tok) h['Authorization'] = 'Bearer ' + tok;
    return Object.assign(h, extra || {});
  }

  // ── State ────────────────────────────────────────────────────────────
  var state = {
    handsFree: false,        // auto-speak replies + auto-listen after
    recording: false,
    speaking: false,
    listening: false,        // auto-listen window open
    recorder: null,
    chunks: [],
    stream: null,
    pressTimer: null,
    pttDown: false,
    sttAvailable: null,      // tri-state until /v1/voice/status answers
    voice: '',               // Kokoro voice name (server default when '')
    speed: 1.0,              // 0.5–2.0 speech rate
    ttsEngine: 'auto'        // pinned TTS engine: auto|sapi|kokoro|elevenlabs
  };

  function loadPrefs() {
    try {
      state.voice = localStorage.getItem('orbit-voice-name') || '';
      state.ttsEngine = localStorage.getItem('orbit-tts-engine') || 'auto';
      var s = parseFloat(localStorage.getItem('orbit-voice-speed'));
      if (!isNaN(s) && s >= 0.5 && s <= 2) state.speed = s;
    } catch (e) {}
  }
  function persistPrefs() {
    try {
      localStorage.setItem('orbit-voice-name', state.voice);
      localStorage.setItem('orbit-voice-speed', String(state.speed));
      localStorage.setItem('orbit-tts-engine', state.ttsEngine);
    } catch (e) {}
  }

  // ── Status ───────────────────────────────────────────────────────────
  function refreshStatus() {
    fetch(_bridge + '/v1/voice/status', { headers: headers() })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) {
        if (!s || !s.ok) return;
        state.sttAvailable = !!s.stt;
        var pill = document.getElementById('voiceEnginePill');
        if (pill) pill.textContent = s.tts === 'elevenlabs' ? 'ELEVENLABS' : (s.tts === 'kokoro' ? 'KOKORO VOICE' : 'SAPI VOICE');
        var ntp = document.getElementById('ntpVoiceCard');
        if (ntp) ntp.textContent = 'Voice: ' + (s.tts === 'elevenlabs' ? 'ElevenLabs neural' : s.tts === 'kokoro' ? 'Kokoro local neural' : 'Windows SAPI');
      })
      .catch(function () {});
  }

  // ── TTS: speak assistant replies ─────────────────────────────────
  var _stripRx = [
    [/```[\s\S]*?```/g, ' code block omitted. '],
    [/`([^`]+)`/g, '$1'],
    [/!?\[([^\]]*)\]\(([^)]*)\)/g, '$1'],
    [/^\s{0,3}#{1,6}\s+/gm, ''],
    [/(\*\*|__|\*|~~)/g, ''],
    [/^\s*[-*+]\s+/gm, '']
  ];
  function speakable(text) {
    var t = text || '';
    _stripRx.forEach(function (p) { t = t.replace(p[0], p[1]); });
    t = t.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, '');
    return t.replace(/\s+/g, ' ').trim();
  }

  // Sentence streaming: local Kokoro runs ~4× slower than real-time on this
  // machine, so a whole reply rendered before playback means long silences.
  // Split into sentences, synthesize+play each in sequence — first audio
  // lands after ~one sentence of synthesis, the rest pipeline behind it.
  var currentAudio = null;
  var speakSeq = 0;         // cancels stale sequences
  var speakQueue = [];      // pending sentence fetches
  var playing = false;

  function _playBlob(blob) {
    return new Promise(function (resolve) {
      var url = URL.createObjectURL(blob);
      currentAudio = new Audio(url);
      currentAudio.onended = currentAudio.onerror = function () {
        URL.revokeObjectURL(url);
        resolve(true);
      };
      currentAudio.play().catch(function () { resolve(false); });
    });
  }

  function _drainQueue(seq) {
    if (seq !== speakSeq) return Promise.resolve(false); // superseded
    var next = speakQueue.shift();
    if (!next) {
      state.speaking = false;
      setMatrix && setMatrix('idle');
      if (state.handsFree && state.sttAvailable) autoListen();
      return Promise.resolve(true);
    }
    playing = true;
    return next.fetchPromise
      .then(function (d) {
        if (seq !== speakSeq) return false;
        if (!d || !d.ok) throw new Error((d && d.error) || 'tts failed');
        return _playBlob(d.blob);
      })
      .then(function (ok) {
        playing = false;
        if (seq !== speakSeq || ok === false) return ok;
        return _drainQueue(seq); // next sentence (already fetching in parallel)
      })
      .catch(function (err) {
        playing = false;
        state.speaking = false;
        setMatrix && setMatrix('idle');
        try { console.warn('[voice] speak failed:', err); } catch (e) {}
        return false;
      });
  }

  function _fetchTts(text) {
    // Raw binary mode: no base64 envelope, no client-side decode loop.
    // Voice + speed ride along; server clamps and falls back per engine.
    return fetch(_bridge + '/v1/tts', {
      method: 'POST', headers: headers(),
      body: JSON.stringify({
        text: text,
        format: 'raw',
        voice: state.voice,
        speed: state.speed,
        voice_model: state.ttsEngine
      })
    }).then(function (r) {
      if (!r.ok) return r.json().then(function (d) { return { ok: false, error: d.error }; });
      return r.blob().then(function (b) { return { ok: true, blob: b };
      });
    });
  }

  // Sentence streaming: synthesis overlaps playback, so first audio lands
  // after ~one sentence. The splitter guards against false breaks on
  // decimals (3.14), abbreviations (Dr., e.g., vs.), and ellipses.
  var _NOT_SENTENCE_END = /(?:\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|e\.g|i\.e|approx|Capt|Sgt|Lt|Col|Gen|Fig|No)\.|\b\d+\.\d+|\.\.\.)$/i;

  function _splitSentences(text) {
    var parts = (text || '').split(/(?<=[.!?])\s+/);
    var out = [], buf = '';
    for (var i = 0; i < parts.length; i++) {
      var candidate = buf ? buf + ' ' + parts[i] : parts[i];
      if ((candidate.length < 220) && (i === parts.length - 1 || !_NOT_SENTENCE_END.test(parts[i]))) {
        buf = candidate;
      } else {
        if (buf) out.push(buf);
        buf = parts[i];
      }
    }
    if (buf) out.push(buf);
    return out.filter(function (s) { return s.trim().length; });
  }

  function speak(text) {
    if (!state.handsFree) return Promise.resolve(false);
    var clean = speakable(text);
    if (!clean) return Promise.resolve(false);
    stopSpeaking();
    state.speaking = true;
    setMatrix && setMatrix('running');
    var seq = ++speakSeq;
    var sentences = _splitSentences(clean.slice(0, 4500));
    // Start ALL sentence syntheses now (server queues them); playback
    // drains them in order — synthesis of sentence N+1 overlaps playback
    // of sentence N.
    speakQueue = sentences.map(function (s, idx) {
      return { text: s, fetchPromise: _fetchTts(s), idx: idx };
    });
    return _drainQueue(seq);
  }

  function stopSpeaking() {
    speakSeq++;              // invalidate any in-flight sequence
    speakQueue = [];
    playing = false;
    if (currentAudio) {
      try { currentAudio.pause(); } catch (e) {}
      currentAudio = null;
    }
    state.speaking = false;
  }

  // ── STT: record → transcribe → composer ──────────────────────────────
  function startRecording(hold) {
    if (state.recording || state.speaking) return; // self-echo guard: never listen while speaking
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      window.UI && UI.Toast && UI.Toast('err', 'Voice', 'Microphone API unavailable');
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      .then(function (stream) {
        state.stream = stream;
        state.chunks = [];
        state.recorder = new MediaRecorder(stream);
        state.recorder.ondataavailable = function (e) { if (e.data && e.data.size) state.chunks.push(e.data); };
        state.recorder.onstop = function () { transcribeAndFill(hold); };
        state.recorder.start();
        state.recording = true;
        updateMicUI(true);
      })
      .catch(function () {
        window.UI && UI.Toast && UI.Toast('err', 'Microphone blocked', 'Allow mic access to talk to JARVIS');
      });
  }

  function stopRecording() {
    if (!state.recording) return;
    state.recording = false;
    updateMicUI(false);
    try { state.recorder.stop(); } catch (e) {}
    if (state.stream) { state.stream.getTracks().forEach(function (t) { t.stop(); }); state.stream = null; }
  }

  function transcribeAndFill(hold) {
    if (!state.chunks.length) return;
    var blob = new Blob(state.chunks, { type: state.chunks[0].type || 'audio/webm' });
    state.chunks = [];
    if (blob.size < 2048) return; // click noise — ignore
    var fr = new FileReader();
    fr.onload = function () {
      var b64 = fr.result.split(',')[1];
      var sb = document.getElementById('sbInput');
      var placeholder = sb && sb.placeholder;
      if (sb) sb.placeholder = 'Transcribing…';
      fetch(_bridge + '/v1/stt', {
        method: 'POST', headers: headers(),
        body: JSON.stringify({ audio_b64: b64, mime: blob.type })
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (sb) sb.placeholder = placeholder || 'Ask JARVIS anything...';
          if (!res.ok || !res.d.ok) {
            var msg = (res.d && res.d.error) || 'transcription failed';
            window.UI && UI.Toast && UI.Toast(res.ok ? 'err' : 'warn', 'Voice', msg.slice(0, 120));
            if (!state.handsFree) state.handsFree = false, persistVoiceMode(), updateVoiceUI();
            return;
          }
          var text = (res.d.text || '').trim();
          if (!text) return;
          // Untrusted-input boundary: transcript is treated exactly like
          // typed text — composed into the composer for the user to see.
          if (sb) {
            sb.value = (sb.value ? sb.value + ' ' : '') + text;
            sb.focus();
          }
          if (state.handsFree) {
            // Send FIRST — sendToJarvis reads and clears sb.value itself;
            // clearing beforehand would transmit an empty message.
            if (window.sendToJarvis) { sb && (sb.value = text); window.sendToJarvis(); }
            // no sendToJarvis (module race): leave text in the composer for Enter
          }
        })
        .catch(function () {
          if (sb) sb.placeholder = placeholder || 'Ask JARVIS anything...';
          window.UI && UI.Toast && UI.Toast('err', 'Voice', 'STT request failed');
        });
    };
    fr.readAsDataURL(blob);
  }

  // Hands-free: after JARVIS finishes speaking, briefly reopen the mic.
  var _autoListenTimer = null;
  function autoListen() {
    clearTimeout(_autoListenTimer);
    state.listening = true;
    startRecording(false);
    _autoListenTimer = setTimeout(function () {
      if (state.recording) stopRecording();
      state.listening = false;
    }, 6000); // 6s window to start speaking
  }

  // ── Instant acknowledgment (Mark-LIV) ────────────────────────────────
  var _ackRules = [
    [/\b(search|find|look up|google)\b/i, 'Searching now.'],
    [/\b(open|launch|go to|navigate)\b/i, 'Opening it.'],
    [/\b(close|quit|shut)\b/i, 'Closing.'],
    [/\b(play|pause|skip)\b/i, 'On it.'],
    [/\b(volume|mute|louder|quieter)\b/i, 'Adjusting.'],
    [/\b(screenshot|capture)\b/i, 'Capturing.'],
    [/\b(summar(y|ize|ise))\b/i, 'Summarizing.'],
    [/\b(send|type|write|draft)\b/i, 'Writing.']
  ];
  function ackFor(text) {
    var t = (text || '').trim();
    if (t.length < 4 || t.charAt(t.length - 1) === '?') return '';
    for (var i = 0; i < _ackRules.length; i++) {
      if (_ackRules[i][0].test(t)) return _ackRules[i][1];
    }
    return '';
  }
  function speakAckIfTask(text) {
    if (!state.handsFree) return;
    var ack = ackFor(text);
    if (ack) speak(ack);
  }

  // ── Push-to-talk: hold Ctrl+Space (Mark-LIV binding) ─────────────────
  // Esc interrupts playback (hands-free barge-in).
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey && e.code === 'Space' && !state.pttDown) {
      state.pttDown = true;
      e.preventDefault();
      startRecording(true);
    }
    if (e.key === 'Escape' && state.speaking) {
      stopSpeaking();
      window.UI && UI.Toast && UI.Toast('info', 'Voice', 'Stopped speaking');
    }
  });
  document.addEventListener('keyup', function (e) {
    if (e.ctrlKey === false || e.code === 'Space') {
      if (state.pttDown) { state.pttDown = false; stopRecording(); }
    }
  });

  // ── UI: mic button + voice toggle in the composer ────────────────────
  function persistVoiceMode() {
    try { localStorage.setItem('orbit-voice', state.handsFree ? '1' : '0'); } catch (e) {}
  }

  function updateMicUI(on) {
    var btn = document.getElementById('sbMicBtn');
    if (btn) btn.classList.toggle('rec', on);
  }
  function updateVoiceUI() {
    var btn = document.getElementById('sbVoiceBtn');
    if (btn) {
      btn.classList.toggle('on', state.handsFree);
      btn.title = state.handsFree ? 'Hands-free ON — JARVIS speaks and listens'
                                  : 'Hands-free OFF — replies stay silent';
    }
  }

  function injectComposerControls() {
    var bar = document.querySelector('.sb-composer-bar');
    if (!bar || document.getElementById('sbMicBtn')) return;
    var mic = document.createElement('button');
    mic.id = 'sbMicBtn';
    mic.className = 'sb-mic';
    mic.title = 'Push-to-talk (hold Ctrl+Space)';
    mic.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none">' +
      '<path d="M12 15a3 3 0 003-3V6a3 3 0 10-6 0v6a3 3 0 003 3z" stroke="currentColor" stroke-width="1.6"/>' +
      '<path d="M19 11a7 7 0 01-14 0M12 18v3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
    mic.addEventListener('mousedown', function () { startRecording(true); });
    mic.addEventListener('mouseup', function () { stopRecording(); });
    mic.addEventListener('mouseleave', function () { if (state.recording) stopRecording(); });

    var voice = document.createElement('button');
    voice.id = 'sbVoiceBtn';
    voice.className = 'sb-voice';
    voice.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none">' +
      '<path d="M11 5L6 9H3v6h3l5 4V5z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>' +
      '<path d="M15.5 8.5a5 5 0 010 7M18 6a8.5 8.5 0 010 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
    voice.addEventListener('click', function () {
      state.handsFree = !state.handsFree;
      if (!state.handsFree) { stopSpeaking(); clearTimeout(_autoListenTimer); if (state.recording && state.listening) stopRecording(); }
      persistVoiceMode();
      updateVoiceUI();
      window.UI && UI.Toast && UI.Toast('info', 'Voice', state.handsFree ? 'Hands-free on' : 'Hands-free off');
    });

    var grow = bar.querySelector('.sb-grow');
    bar.insertBefore(mic, grow);
    bar.insertBefore(voice, grow);
    updateVoiceUI();
  }

  // ── Hook the chat pipeline: speak every finished JARVIS reply ────────
  function wireReplyHook() {
    if (window.Chat && Chat.endStream && !Chat.endStream.__voiceHooked) {
      var orig = Chat.endStream;
      Chat.endStream = function (text) {
        var r = orig.apply(this, arguments);
        if (text && text !== '(no response)') speak(text);
        return r;
      };
      Chat.endStream.__voiceHooked = true;
    }
    if (window.sendToJarvis && !sendToJarvis.__voiceAckHooked) {
      var origSend = sendToJarvis;
      window.sendToJarvis = function () {
        try {
          var input = document.getElementById('sbInput');
          speakAckIfTask(input ? input.value : '');
        } catch (e) {}
        return origSend.apply(this, arguments);
      };
      sendToJarvis.__voiceAckHooked = true;
    }
  }

  // ── Settings: voice picker + speed + test ────────────────────────────
  function wireSettings() {
    var sel = document.getElementById('settingsVoiceSelect');
    var speed = document.getElementById('settingsVoiceSpeed');
    var speedVal = document.getElementById('settingsVoiceSpeedVal');
    var test = document.getElementById('voiceTestBtn');
    if (!sel || sel.__voiceWired) return;
    sel.__voiceWired = true;

    function fillVoices(list, def) {
      sel.innerHTML = '';
      var optDef = document.createElement('option');
      optDef.value = '';
      optDef.textContent = def ? 'Default (' + def + ')' : 'Default';
      sel.appendChild(optDef);
      (list || []).forEach(function (v) {
        var o = document.createElement('option');
        o.value = v;
        o.textContent = v.replace(/^(af|am|bf|bm)_/, function (m) { return m.toUpperCase(); }).replace(/_/g, ' ');
        sel.appendChild(o);
      });
      sel.value = state.voice || '';
    }

    refreshVoices().then(function (d) {
      if (d && d.ok) fillVoices(d.voices, d.default_voice);
    });

    sel.addEventListener('change', function () {
      state.voice = sel.value;
      persistPrefs();
      stopSpeaking(); // in-flight audio was synthesized with the old voice
    });

    if (speed && speedVal) {
      speed.value = String(state.speed);
      speedVal.textContent = state.speed.toFixed(2) + '\u00d7';
      speed.addEventListener('input', function () {
        speedVal.textContent = parseFloat(speed.value).toFixed(2) + '\u00d7';
      });
      speed.addEventListener('change', function () {
        setSpeed(speed.value);
        stopSpeaking();
      });
    }

    if (test) {
      test.addEventListener('click', function () {
        // Temporarily allow speaking even outside hands-free for the sample.
        var wasHandsFree = state.handsFree;
        state.handsFree = true;
        speak('Voice check. I am JARVIS, running locally on this machine.');
        state.handsFree = wasHandsFree;
      });
    }
  }

  function refreshVoices() {
    return fetch(_bridge + '/v1/voices', { headers: headers() })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  // Settings DOM is static (index.html); wire when the page exists.
  var _settingsTries = 0;
  function wireSettingsWhenReady() {
    wireSettings();
    if (!document.getElementById('settingsVoiceSelect') && ++_settingsTries < 20) {
      setTimeout(wireSettingsWhenReady, 500);
    }
  }

  // ── Boot ─────────────────────────────────────────────────────────────
  function boot() {
    loadPrefs();
    try { state.handsFree = localStorage.getItem('orbit-voice') === '1'; } catch (e) {}
    injectComposerControls();
    updateVoiceUI();
    refreshStatus();
    wireReplyHook();
    wireSettingsWhenReady();
    wireMainComposerVoice();
    var tries = 0;
    var t = setInterval(function () {
      wireReplyHook();
      if (++tries > 20) clearInterval(t);
    }, 1000); // late-loaded modules
  }

  // ── Main composer voice engine selector ─────────────────────────────
  // The AI-drawer composer has its own voice button and engine menu. This
  // picker pins WHICH ENGINE renders (auto|sapi|kokoro|elevenlabs); it is
  // deliberately separate from state.voice, which is the Kokoro voice NAME
  // used by the settings picker. Options are reconciled against the live
  // /v1/voice/status chain so engines that are not available are dimmed
  // rather than silently failing at synthesis time.
  var ENGINE_LABELS = {
    auto: 'Auto',
    sapi: 'SAPI (Windows)',
    kokoro: 'Kokoro (local)',
    elevenlabs: 'ElevenLabs'
  };

  function wireMainComposerVoice() {
    var voiceBtn = document.getElementById('voiceButton');
    var engBtn = document.getElementById('voiceModelButton');
    var engMenu = document.getElementById('voiceModelMenu');
    var engName = document.getElementById('voiceModelName');
    if (!voiceBtn || !engBtn || !engMenu || engMenu.__wired) return;
    engMenu.__wired = true;

    function label(engine) {
      return ENGINE_LABELS[engine] || engine;
    }

    function paint() {
      engName.textContent = label(state.ttsEngine);
      var opts = engMenu.querySelectorAll('.model-option[data-voice]');
      for (var i = 0; i < opts.length; i++) {
        var key = opts[i].getAttribute('data-voice');
        var on = key === state.ttsEngine;
        opts[i].classList.toggle('active', on);
        opts[i].setAttribute('aria-selected', on ? 'true' : 'false');
        var dot = opts[i].querySelector('.dot');
        if (!dot) {
          dot = document.createElement('span');
          dot.className = 'dot';
          opts[i].insertBefore(dot, opts[i].firstChild);
        }
        dot.classList.toggle('on', on);
      }
    }

    function closeMenu() {
      engMenu.classList.remove('open');
      engMenu.removeAttribute('data-open');
    }

    engBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = engMenu.classList.toggle('open');
      engMenu.setAttribute('data-open', open ? 'true' : 'false');
    });

    // Outside click closes the menu. Deferred by one tick so it never
    // swallows the same click that opened it.
    setTimeout(function () {
      document.addEventListener('click', function (e) {
        if (!engBtn.contains(e.target) && !engMenu.contains(e.target)) closeMenu();
      });
    }, 0);

    engMenu.addEventListener('click', function (e) {
      var opt = e.target.closest ? e.target.closest('.model-option') : null;
      if (!opt || opt.disabled) return;
      state.ttsEngine = opt.getAttribute('data-voice') || 'auto';
      persistPrefs();
      paint();
      closeMenu();
      // Stop in-flight audio: it was rendered by the previous engine.
      stopSpeaking();
      window.UI && UI.Toast && UI.Toast('info', 'Voice', label(state.ttsEngine));
    });

    voiceBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      state.handsFree = !state.handsFree;
      if (!state.handsFree) {
        stopSpeaking();
        clearTimeout(_autoListenTimer);
        if (state.recording && state.listening) stopRecording();
      }
      try { localStorage.setItem('orbit-voice', state.handsFree ? '1' : '0'); } catch (err) {}
      updateVoiceUI();
      voiceBtn.classList.toggle('active', state.handsFree);
      window.UI && UI.Toast && UI.Toast(
        'info', 'Voice', state.handsFree ? 'Hands-free on' : 'Hands-free off');
    });

    voiceBtn.classList.toggle('active', state.handsFree);
    paint();

    // Reconcile the menu against the live engine chain from the bridge.
    fetch(_bridge + '/v1/voice/status', { method: 'POST', headers: headers() })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.ok) return;
        var live = (d.voice_menu && d.voice_menu.engines) || d.tts_chain || [];
        var opts = engMenu.querySelectorAll('.model-option[data-voice]');
        for (var i = 0; i < opts.length; i++) {
          var key = opts[i].getAttribute('data-voice');
          if (key === 'auto') continue;
          var available = live.indexOf(key) !== -1;
          opts[i].disabled = !available;
          opts[i].title = available ? '' : 'Not available on this machine';
          opts[i].style.opacity = available ? '' : '0.4';
        }
        paint();
      })
      .catch(function () { /* menu stays usable with the static labels */ });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  window.JarvisVoice = {
    speak: speak, stopSpeaking: stopSpeaking, ackFor: ackFor, state: state,
    setVoice: function (name) { state.voice = name || ''; persistPrefs(); },
    setSpeed: function (s) { var v = parseFloat(s); if (!isNaN(v)) { state.speed = Math.max(0.5, Math.min(2, v)); persistPrefs(); } return state.speed; },
    refreshVoices: function () {
      return fetch(_bridge + '/v1/voices', { headers: headers() })
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; });
    }
  };
})();
