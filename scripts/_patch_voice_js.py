"""Rewrite wireMainComposerVoice in orbit-browser/src/js/voice.js.

Replaces the flawed block (which clobbered state.voice, used a relative
fetch URL, referenced a non-existent state._autoListenTimer and could
double-wire) with a correct engine picker that keeps the engine pin
separate from the Kokoro voice NAME and reconciles options against the
live /v1/voice/status chain.
"""

from pathlib import Path

TARGET = Path("orbit-browser/src/js/voice.js")

NEW_BLOCK = r"""  // ── Main composer voice engine selector ─────────────────────────────
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
"""


def main() -> None:
    lines = TARGET.read_text(encoding="utf-8").split("\n")

    # 0-indexed bounds of the block to replace.
    start = next(
        i for i, l in enumerate(lines)
        if "Main composer voice engine selector" in l
    )
    # The block runs until the line before the readyState bootstrap.
    end = next(
        i for i, l in enumerate(lines)
        if "document.readyState === 'loading'" in l
    )
    # Trim the bootstrap's preceding blank line out of the block.
    while end > start and lines[end - 1].strip() == "":
        end -= 1

    print("replacing 0-idx [%d:%d]" % (start, end))

    new_lines = lines[:start] + NEW_BLOCK.rstrip("\n").split("\n") + lines[end:]
    TARGET.write_text("\n".join(new_lines), encoding="utf-8")
    print("wrote", TARGET, "lines:", len(new_lines))


if __name__ == "__main__":
    main()