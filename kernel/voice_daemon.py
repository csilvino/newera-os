"""Newera OS Neural Voice Daemon v1.3 (Hands-Free Always-On VAD + Anti-Echo + Neural TTS PT-BR).
- Starts listening automatically on boot (no button click needed!).
- Detects when you speak via RMS Voice Activity Detection (VAD), records until ~1.1s of silence,
  transcribes with faster-whisper (base/int8), and sends to Continuum Bridge.
- Automatically pauses mic capture while Newera is speaking (zero self-echo).
"""

from __future__ import annotations

import asyncio
import math
import os
import queue
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IPC_DIR = ROOT / "data" / "ipc"
IPC_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_STATE_FILE = IPC_DIR / "audio_state.txt"
VOICE_CMD_FILE = IPC_DIR / "voice_cmd.txt"
SPOKEN_INTENT_FILE = IPC_DIR / "spoken_intent.txt"
VOICE_LOG_FILE = IPC_DIR / "voice_debug.log"

VOICE_NAME = os.getenv("NEWERA_VOICE", "pt-BR-AntonioNeural")
VAD_SPEECH_THRESHOLD = int(os.getenv("NEWERA_VAD_THRESHOLD", "44"))  # VU 0..100 trigger level

_speak_queue: queue.Queue[str] = queue.Queue()
_is_speaking = False
_is_listening = False
_current_mic_level = 0
_whisper_model = None
_rec_lock = threading.Lock()
_rec_chunks: list = []
_utterance_queue: queue.Queue = queue.Queue()
_music_proc: subprocess.Popen | None = None
_music_lock = threading.Lock()


def _log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(VOICE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _register_nvidia_dlls() -> None:
    """Adds pip-installed nvidia-cublas-cu12 and nvidia-cudnn-cu12 DLL folders on Windows."""
    if os.name != "nt":
        return
    import sys

    site_pkgs = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    if not site_pkgs.exists():
        return
    for bin_dir in site_pkgs.glob("*/bin"):
        if bin_dir.is_dir():
            try:
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            except Exception:
                pass


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        _register_nvidia_dlls()
        from faster_whisper import WhisperModel

        try:
            _log("[NEWERA-VOICE] Carregando faster-whisper (base/float16) 100% GPU na RTX 3060...")
            _whisper_model = WhisperModel("base", device="cuda", compute_type="float16")
            _log("[NEWERA-VOICE] faster-whisper ATIVO NA GPU CUDA (RTX 3060)!")
        except Exception as exc:
            _log(f"[NEWERA-VOICE] CUDA indisponível ({exc}), usando CPU int8...")
            _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            _log("[NEWERA-VOICE] faster-whisper pronto (CPU)!")
    return _whisper_model


def _play_mp3_fast_windows(mp3_path: Path) -> None:
    """Zero-startup MP3 playback on the Windows host via native winmm.dll MCI (replaces powershell.exe)."""
    import ctypes

    mci = ctypes.windll.winmm.mciSendStringW
    alias = f"nwr_{int(time.time() * 1000) % 100000}"
    path_str = str(mp3_path.resolve())
    mci(f'open "{path_str}" type mpegvideo alias {alias}', None, 0, None)
    mci(f"play {alias} wait", None, 0, None)
    mci(f"close {alias}", None, 0, None)


def _speak_sapi_offline(text: str) -> None:
    safe = text.replace("'", " ").replace("\n", " ")[:400]
    ps_script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak('{safe}')"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


async def _synthesize_edge_tts(text: str, out_path: Path) -> bool:
    try:
        import edge_tts

        communicate = edge_tts.Communicate(text, VOICE_NAME, rate="+5%")
        await communicate.save(str(out_path))
        return out_path.exists() and out_path.stat().st_size > 100
    except Exception:
        return False


def speak_now(text: str) -> None:
    global _is_speaking
    clean = " ".join(text.replace("•", ",").replace("|", " ").split())[:420]
    if not clean:
        return
    _log(f"[VOICE-TTS] Falando: {clean[:90]}")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        mp3_path = Path(tmp.name)
    try:
        _is_speaking = True
        ok = asyncio.run(_synthesize_edge_tts(clean, mp3_path))
        if ok:
            _play_mp3_fast_windows(mp3_path)
        else:
            _speak_sapi_offline(clean)
    finally:
        time.sleep(0.25)
        _is_speaking = False
        mp3_path.unlink(missing_ok=True)


def _tts_worker() -> None:
    while True:
        text = _speak_queue.get()
        try:
            speak_now(text)
        except Exception as exc:
            _log(f"[VOICE-TTS] Error: {exc}")
        finally:
            _speak_queue.task_done()


def _transcribe_worker() -> None:
    """Consumes completed VAD speech utterances, transcribes with faster-whisper, and sends to Bridge."""
    import numpy as np

    # Pre-warm Whisper immediately at startup so first spoken phrase has zero delay
    _get_whisper()

    while True:
        chunks = _utterance_queue.get()
        try:
            audio = np.concatenate(chunks, axis=0)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = Path(tmp.name)
            try:
                with wave.open(str(wav_path), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(audio.tobytes())

                model = _get_whisper()
                segments, _ = model.transcribe(str(wav_path), language="pt", vad_filter=True)
                spoken = " ".join(seg.text.strip() for seg in segments).strip()
            finally:
                wav_path.unlink(missing_ok=True)

            if len(spoken) >= 2:
                _log(f"[VOCÊ FALOU] {spoken}")
                SPOKEN_INTENT_FILE.write_text(spoken, encoding="utf-8")
        except Exception as exc:
            _log(f"[VOICE-STT] Error: {exc}")
        finally:
            _utterance_queue.task_done()


def _handsfree_mic_vad_worker() -> None:
    """Always-on microphone stream with real-time VU meter + automatic VAD speech capture."""
    global _current_mic_level, _is_listening
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:
        _log(f"[VOICE-VU] Missing audio libs: {exc}")
        return

    pre_roll: list = []
    speech_chunks: list = []
    in_speech = False
    speech_frames = 0
    silence_frames = 0

    def _callback(indata, _frames, _time_info, _status):
        nonlocal in_speech, speech_frames, silence_frames, speech_chunks, pre_roll
        global _current_mic_level, _is_listening

        samples = indata[:, 0].astype(np.float32)
        rms = float(np.sqrt(np.mean(samples * samples)))
        if rms < 1e-5:
            lvl = 0
        else:
            db = 20.0 * math.log10(rms + 1e-7)
            lvl = int(min(100, max(0, (db + 55.0) * 2.2)))
        _current_mic_level = lvl

        # Anti-echo: ignore mic capture while Newera is speaking
        if _is_speaking:
            in_speech = False
            _is_listening = False
            speech_chunks.clear()
            pre_roll.clear()
            return

        pcm16 = np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)

        if not in_speech:
            pre_roll.append(pcm16.copy())
            if len(pre_roll) > 4:  # keep ~0.4s pre-roll so start of word isn't clipped
                pre_roll.pop(0)
            if lvl >= VAD_SPEECH_THRESHOLD:
                speech_frames += 1
                if speech_frames >= 2:  # ~0.2s above threshold confirms real voice
                    in_speech = True
                    _is_listening = True
                    silence_frames = 0
                    speech_chunks = list(pre_roll)
                    pre_roll.clear()
            else:
                speech_frames = 0
        else:
            speech_chunks.append(pcm16.copy())
            if lvl < VAD_SPEECH_THRESHOLD - 6:
                silence_frames += 1
            else:
                silence_frames = 0

            # Finish utterance after ~0.7s of silence or max 8s
            if silence_frames >= 7 or len(speech_chunks) >= 80:
                in_speech = False
                _is_listening = False
                speech_frames = 0
                silence_frames = 0
                if len(speech_chunks) >= 6:  # ignore tiny clicks < 0.6s
                    _utterance_queue.put(list(speech_chunks))
                speech_chunks.clear()

    try:
        with sd.InputStream(channels=1, samplerate=16000, blocksize=1600, dtype="float32", callback=_callback):
            while True:
                pkt = f"AUDIO|{_current_mic_level}|{1 if _is_speaking else 0}|{1 if _is_listening else 0}"
                try:
                    AUDIO_STATE_FILE.write_text(pkt, encoding="utf-8")
                except Exception:
                    pass
                time.sleep(0.08)
    except Exception as exc:
        _log(f"[VOICE-VU] Mic stream error: {exc}")


def _find_app_player_exe() -> str | None:
    """Finds Edge or Chrome on Windows to launch a clean frameless YouTube video player window."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def stop_background_music() -> None:
    global _music_proc
    with _music_lock:
        if _music_proc is not None and _music_proc.poll() is None:
            pid = _music_proc.pid
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                _music_proc.terminate()
            try:
                _music_proc.wait(timeout=1.5)
            except Exception:
                _music_proc.kill()
        _music_proc = None
    _log("[NEWERA-MUSIC] Player de vídeo encerrado.")


def play_youtube_background(query: str) -> None:
    """Searches YouTube via yt-dlp (fast flat search) and opens a clean frameless video player window."""
    global _music_proc
    stop_background_music()
    _log(f"[NEWERA-MUSIC] Pesquisando no YouTube: '{query}'...")
    try:
        import yt_dlp

        ydl_opts = {
            "extract_flat": "in_playlist",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if "entries" in info and info["entries"]:
                info = info["entries"][0]
            video_id = info.get("id")
            title = info.get("title", query)

        if not video_id:
            _speak_queue.put(f"Não consegui encontrar o vídeo de {query}.")
            return

        watch_url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
        _log(f"[NEWERA-MUSIC] Abrindo player: {title} ({watch_url})")
        _speak_queue.put(f"Abrindo {title} no player.")

        player_exe = _find_app_player_exe()
        if player_exe:
            profile_dir = IPC_DIR / "yt_player_profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            with _music_lock:
                _music_proc = subprocess.Popen(
                    [
                        player_exe,
                        f"--app={watch_url}",
                        f"--user-data-dir={profile_dir}",
                        "--autoplay-policy=no-user-gesture-required",
                        "--window-size=960,540",
                        "--window-position=160,100",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        else:
            os.startfile(watch_url)
    except Exception as exc:
        _log(f"[NEWERA-MUSIC] Erro ao abrir YouTube: {exc}")
        _speak_queue.put("Não consegui abrir esse vídeo agora.")


def _ipc_command_watcher() -> None:
    _log(f"[NEWERA-VOICE] Hands-Free VAD + Neural TTS ({VOICE_NAME}) + YouTube Player ativo!")
    while True:
        try:
            if VOICE_CMD_FILE.exists():
                cmd = VOICE_CMD_FILE.read_text(encoding="utf-8", errors="replace").strip()
                VOICE_CMD_FILE.unlink(missing_ok=True)
                if cmd.startswith("SPEAK|"):
                    phrase = cmd[len("SPEAK|") :].strip()
                    if phrase:
                        _speak_queue.put(phrase)
                elif cmd.startswith("PLAY_YT|"):
                    query = cmd[len("PLAY_YT|") :].strip()
                    if query:
                        threading.Thread(target=play_youtube_background, args=(query,), daemon=True).start()
                elif cmd.startswith("STOP_MUSIC|"):
                    stop_background_music()
        except Exception:
            pass
        time.sleep(0.05)


def run_daemon() -> None:
    VOICE_CMD_FILE.unlink(missing_ok=True)
    SPOKEN_INTENT_FILE.unlink(missing_ok=True)
    threading.Thread(target=_tts_worker, daemon=True).start()
    threading.Thread(target=_transcribe_worker, daemon=True).start()
    threading.Thread(target=_ipc_command_watcher, daemon=True).start()
    threading.Thread(target=_handsfree_mic_vad_worker, daemon=True).start()
    threading.Event().wait()


if __name__ == "__main__":
    import sys

    if "--test-tts" in sys.argv:
        speak_now("Olá! Eu sou o Newera OS, rodando com voz neural em português brasileiro.")
    else:
        run_daemon()
