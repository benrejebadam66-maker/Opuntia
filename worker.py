from PyQt5.QtCore import QThread, pyqtSignal
import os
import re
import time
import audioop
import io
import wave
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

import requests

try:
    import speech_recognition as sr
except Exception:
    sr = None


class WorkerThread(QThread):
    finished = pyqtSignal(str)
    runtime_meta = pyqtSignal(dict)

    def __init__(self, agent, command):
        super().__init__()
        self.agent = agent
        self.command = command

    def _emit_phase(self, phase):
        try:
            self.runtime_meta.emit({"phase": phase})
        except Exception:
            pass

    def run(self):
        try:
            _cmd = (self.command or "").strip()
            self._emit_phase("thinking")
            # Simple routing/context parsing (truthful lightweight step)
            if _cmd.upper().startswith("MODE_TASK::") or _cmd.upper().startswith("AUTH_OK::") or _cmd.upper().startswith("SCREEN_SHARE::"):
                _ = _cmd.split("::", 1)
            # Enter model call
            if hasattr(self.agent, "process_command"):
                response = self.agent.process_command(self.command)
            elif hasattr(self.agent, "process"):
                response = self.agent.process(self.command)
            else:
                response = f"Command received: {self.command}"
            self.finished.emit(response)
            try:
                meta = self.agent.get_ai_runtime_status() if hasattr(self.agent, "get_ai_runtime_status") else {}
                if isinstance(meta, dict):
                    self.runtime_meta.emit(meta)
            except Exception:
                pass
        except Exception as e:
            self.finished.emit(f"Error: {str(e)}")


class VoiceInputThread(QThread):
    transcribed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, timeout=2.0, phrase_time_limit=20, agent=None):
        super().__init__()
        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit
        self._stop_requested = False
        self._muted_until = 0.0   # epoch timestamp â€” discard audio captured before this
        self.agent = agent  # used for correction context
        self.groq_api_key = (os.getenv("GROQ_API_KEY") or "").strip()
        self.groq_stt_model = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
        self.stt_lang_hints = [s.strip() for s in (os.getenv("VOICE_LANG_HINTS", "en-US") or "").split(",") if s.strip()]
        self._race_google = (os.getenv("VOICE_RACE_GOOGLE", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.voice_sensitivity = (os.getenv("VOICE_SENSITIVITY", "high").strip().lower())
        self.voice_min_rms = int(os.getenv("VOICE_MIN_RMS", "6"))
        self.voice_noise_mult = float(os.getenv("VOICE_NOISE_MULT", "0.7"))
        self.voice_min_chunk_sec = float(os.getenv("VOICE_MIN_CHUNK_SEC", "0.10"))
        # Target RMS for audio normalization before sending to STT
        self.voice_target_rms = int(os.getenv("VOICE_TARGET_RMS", "4400"))
        self.voice_max_amplify = float(os.getenv("VOICE_MAX_AMPLIFY", "30.0"))
        self.voice_calibration_sec = float(os.getenv("VOICE_CALIBRATION_SEC", "1.2"))
        self.voice_sample_rate = int(os.getenv("VOICE_SAMPLE_RATE", "16000"))
        self.voice_chunk_size = int(os.getenv("VOICE_CHUNK_SIZE", "1024"))
        self.voice_device_index = os.getenv("VOICE_DEVICE_INDEX", "").strip()
        # Language for Whisper (primary language hint â€” use your language code)
        self.whisper_language = (os.getenv("WHISPER_LANGUAGE", "en").strip())  # e.g. "en", "fr", "ar"
        # Prompt hint improves Whisper accuracy for domain-specific words
        self.whisper_prompt = os.getenv("WHISPER_PROMPT", "PÃ©ar, open, search, click, close, browser, screen, file, window")
        self._last_norm_text = ""
        self._last_emit_ts = 0.0
        self._noise_floor_rms = 80
        self._no_text_count = 0
        self._last_no_text_ts = 0.0

    def stop_listening(self):
        self._stop_requested = True

    def mute_for(self, seconds):
        """Discard any audio captured in the next N seconds (AI is processing/speaking)."""
        self._muted_until = time.time() + seconds

    def unmute(self, cooldown=1.5):
        """Release the mute with a short cooldown so echoes die out."""
        self._muted_until = time.time() + cooldown

    def _normalize_transcript(self, text):
        norm = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
        norm = re.sub(r"\s+", " ", norm).strip()
        return norm

    def _clean_transcript(self, text):
        t = (text or "").strip()
        if not t:
            return ""
        # Remove repeated trailing filler caused by STT instability.
        t = re.sub(r"\b(uh+|um+|hmm+)\b", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+", " ", t).strip(" ,.")
        return t

    def _should_emit_text(self, text, duration=0.0, rms=0):
        norm = self._normalize_transcript(text)
        if not norm or len(norm) < 2:
            return False

        # Hard-drop known Whisper hallucinations on silence/noise.
        ghost_phrases = {
            # gratitude hallucinations
            "thank you", "thanks", "thank you very much", "thanks you", "thankyou",
            "thank you for watching", "thanks for watching", "thanks for watching this video",
            # single filler words Whisper outputs on silence
            "you", "bye", "bye bye", "goodbye", "yes", "no", "okay", "ok", "hmm", "hm",
            "uh", "um", "ah", "oh", "well", "so", "like", "right", "sure",
            # YouTube/video hallucinations
            "please subscribe", "subscribe", "like and subscribe",
            "please like and subscribe", "don t forget to subscribe",
            # music/punctuation-only transcripts
            "music", "applause", "laughter", "silence",
            # common random Whisper outputs
            "i", "i i", "i i i", "the", "a", "an", "and", "or", "but",
            "hi", "hello", "hey", "hey hey",
        }
        words = norm.split()
        # Always drop single-word outputs that are in ghost set
        if len(words) == 1 and norm in ghost_phrases:
            return False
        # Drop ghost phrases when audio is short or quiet (likely silence trigger)
        if norm in ghost_phrases and (duration <= 2.0 or rms < max(160, int(self._noise_floor_rms * 1.6))):
            return False
        # Drop anything that's only punctuation/symbols after normalization
        if not re.search(r"[a-z]", norm):
            return False

        now = time.time()
        # Drop immediate duplicates, common with silence-trigger false positives.
        if norm == self._last_norm_text and (now - self._last_emit_ts) < 10:
            return False

        # Extra cooldown guard for common hallucinated idle phrases.
        if norm in ghost_phrases and norm == self._last_norm_text and (now - self._last_emit_ts) < 25:
            return False

        self._last_norm_text = norm
        self._last_emit_ts = now
        return True

    def _audio_stats(self, audio):
        """Return (has_voice, duration_sec, rms)."""
        try:
            raw = audio.frame_data
            if not raw:
                return False, 0.0, 0
            sample_width = max(1, int(audio.sample_width or 2))
            sample_rate = max(1, int(audio.sample_rate or 16000))
            duration = len(raw) / float(sample_rate * sample_width)
            rms = audioop.rms(raw, sample_width)
            if duration < self.voice_min_chunk_sec:
                return False, duration, rms
            threshold = max(self.voice_min_rms, int(self._noise_floor_rms * self.voice_noise_mult))
            # For longer chunks (â‰¥1.0s), attempt transcription even if quiet â€” real speech.
            # Short + quiet = breath noise / mic bump â†’ drop immediately.
            if rms < threshold and duration < 0.1:
                return False, duration, rms
            return True, duration, rms
        except Exception:
            return True, 0.0, 0

    def _amplify_wav(self, raw_pcm, sample_width=2):
        """Boost quiet audio to a target RMS level before sending to STT."""
        try:
            current_rms = audioop.rms(raw_pcm, sample_width)
            if current_rms < 5:
                return raw_pcm  # silence â€” don't amplify
            gain = min(self.voice_max_amplify, self.voice_target_rms / current_rms)
            if gain <= 1.05:
                return raw_pcm  # already loud enough
            return audioop.mul(raw_pcm, sample_width, gain)
        except Exception:
            return raw_pcm

    def _build_amplified_wav(self, audio):
        """Return a WAV bytes buffer at 16kHz/16-bit with amplification applied."""
        raw = audio.get_wav_data(convert_rate=self.voice_sample_rate, convert_width=2)
        # raw is a full WAV file; extract PCM, amplify, repack
        try:
            with io.BytesIO(raw) as wav_in:
                with wave.open(wav_in) as wf:
                    n_channels = wf.getnchannels()
                    sampwidth = wf.getsampwidth()
                    framerate = wf.getframerate()
                    pcm = wf.readframes(wf.getnframes())
            pcm_amp = self._amplify_wav(pcm, sampwidth)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf_out:
                wf_out.setnchannels(n_channels)
                wf_out.setsampwidth(sampwidth)
                wf_out.setframerate(framerate)
                wf_out.writeframes(pcm_amp)
            return buf.getvalue()
        except Exception:
            return raw

    def _transcribe_with_groq(self, audio):
        if not self.groq_api_key:
            return ""
        try:
            wav_data = self._build_amplified_wav(audio)
            data = {
                "model": self.groq_stt_model,
                "temperature": "0",
                # verbose_json gives us no_speech_prob per segment â€” key for silence detection
                "response_format": "verbose_json",
            }
            if self.whisper_language:
                data["language"] = self.whisper_language
            if self.whisper_prompt:
                data["prompt"] = self.whisper_prompt
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.groq_api_key}"},
                files={"file": ("speech.wav", wav_data, "audio/wav")},
                data=data,
                timeout=20,
            )
            if response.status_code >= 400:
                return ""
            payload = response.json() if "application/json" in (response.headers.get("Content-Type", "")) else {}
            # Reject if Whisper itself says this is likely silence/noise
            segments = payload.get("segments") or []
            if segments:
                avg_no_speech = sum(s.get("no_speech_prob", 0.0) for s in segments) / len(segments)
                if avg_no_speech > 0.80:
                    return ""
                # avg_logprob close to 0 = confident; < -1.0 = very uncertain transcription
                avg_logprob = sum(s.get("avg_logprob", 0.0) for s in segments) / len(segments)
                if avg_logprob < -1.5:
                    return ""
            return (payload.get("text") or "").strip()
        except Exception:
            return ""

    def _transcribe_with_google(self, recognizer, audio):
        langs = self.stt_lang_hints or ["en-US"]
        for lang in langs:
            try:
                text = recognizer.recognize_google(audio, language=lang).strip()
                if text:
                    return text
            except sr.UnknownValueError:
                continue
            except Exception:
                continue
        return ""

    def _get_correction_context(self):
        """Return the last few conversation turns as plain text for correction context."""
        try:
            if self.agent is None:
                return ""
            history = list(getattr(self.agent, "conversation_history", []))[-4:]
            lines = []
            for entry in history:
                role = entry.get("role", "")
                content = (entry.get("content") or "")[:120]
                if role == "user":
                    lines.append(f"User: {content}")
                elif role == "assistant":
                    lines.append(f"PÃ©ar: {content}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _ai_correct_transcript(self, raw_text):
        """Use a fast Groq call to fix obvious Whisper misheard words using conversation context."""
        if not self.groq_api_key or not raw_text or len(raw_text.split()) < 2:
            return raw_text
        try:
            ctx = self._get_correction_context()
            context_block = f"Recent conversation:\n{ctx}\n\n" if ctx else ""
            prompt = (
                f"{context_block}"
                f"Voice recognition transcript: \"{raw_text}\"\n\n"
                "Fix ONLY obvious transcription errors: misheard words that sound similar, "
                "wrong proper nouns (e.g. the assistant is called 'PÃ©ar'), garbled commands. "
                "If it looks correct, return it unchanged. "
                "Reply with ONLY the corrected sentence, nothing else."
            )
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.groq_api_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 120,
                    "temperature": 0,
                },
                timeout=4,
            )
            if response.status_code == 200:
                corrected = (response.json()["choices"][0]["message"]["content"] or "").strip()
                # Sanity: reject if the correction is drastically different in length
                if corrected and 0.35 < len(corrected) / max(1, len(raw_text)) < 3.0:
                    return corrected
        except Exception:
            pass
        return raw_text

    def _transcribe_fast(self, recognizer, audio):
        """Race STT backends, return first usable transcript, then AI-correct it."""
        raw = ""
        if not self._race_google:
            raw = self._transcribe_with_groq(audio)
            if not raw:
                raw = self._transcribe_with_google(recognizer, audio)
        else:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = []
                futures.append(pool.submit(self._transcribe_with_groq, audio))
                futures.append(pool.submit(self._transcribe_with_google, recognizer, audio))
                done, pending = wait(futures, timeout=8, return_when=FIRST_COMPLETED)
                for f in done:
                    try:
                        text = (f.result() or "").strip()
                        if text:
                            raw = text
                            for p in pending:
                                p.cancel()
                            break
                    except Exception:
                        pass
                if not raw:
                    done2, _ = wait(futures, timeout=4)
                    for f in done2:
                        try:
                            text = (f.result() or "").strip()
                            if text:
                                raw = text
                                break
                        except Exception:
                            pass
        if not raw:
            return ""
        # AI correction pass â€” fixes misheard words using conversation context
        return self._ai_correct_transcript(raw)

    def _get_microphone_candidates(self):
        """Return (candidate_device_indexes, device_names, error_message)."""
        try:
            device_names = sr.Microphone.list_microphone_names()
        except Exception:
            device_names = []
        if not device_names:
            return [], [], (
                "No microphone devices detected. Check Windows microphone privacy settings, "
                "and make sure a mic is connected and enabled."
            )
        if self.voice_device_index:
            try:
                idx = int(self.voice_device_index)
            except Exception:
                return [], device_names, (
                    f"VOICE_DEVICE_INDEX '{self.voice_device_index}' is not a valid number. "
                    f"Available devices: {', '.join(device_names)}"
                )
            if idx < 0 or idx >= len(device_names):
                return [], device_names, (
                    f"VOICE_DEVICE_INDEX {idx} is out of range. "
                    f"Available devices: {', '.join(device_names)}"
                )
            return [idx], device_names, ""
        # Try default device first, then fall back to explicit indexes
        return [None] + list(range(len(device_names))), device_names, ""

    def _capture_loop(self, recognizer, source):
        # Longer calibration = more accurate noise floor measurement
        recognizer.adjust_for_ambient_noise(source, duration=self.voice_calibration_sec)
        if self.voice_sensitivity == "high":
            # Quiet speaker mode: push threshold down aggressively
            recognizer.energy_threshold = max(30, int(recognizer.energy_threshold * 0.40))
            self._noise_floor_rms = max(14, int(recognizer.energy_threshold * 0.16))
        elif self.voice_sensitivity == "low":
            recognizer.energy_threshold = max(200, int(recognizer.energy_threshold * 1.05))
            self._noise_floor_rms = max(70, int(recognizer.energy_threshold * 0.40))
        else:
            recognizer.energy_threshold = max(120, int(recognizer.energy_threshold * 0.80))
            self._noise_floor_rms = max(45, int(recognizer.energy_threshold * 0.32))
        # Allow slow re-adaptation (helps in changing noise environments)
        recognizer.dynamic_energy_threshold = True
        recognizer.dynamic_energy_adjustment_damping = 0.10
        recognizer.dynamic_energy_ratio = 1.05
        while not self._stop_requested:
            try:
                audio = recognizer.listen(
                    source,
                    timeout=self.timeout,
                    phrase_time_limit=self.phrase_time_limit,
                )
            except sr.WaitTimeoutError:
                continue
            if self._stop_requested:
                break
            # Discard audio captured while AI is processing or during echo cooldown
            if time.time() < self._muted_until:
                continue
            has_voice, duration, rms = self._audio_stats(audio)
            if not has_voice:
                continue
            text = self._transcribe_fast(recognizer, audio)
            text = self._clean_transcript(text)
            if text and self._should_emit_text(text, duration=duration, rms=rms):
                self._no_text_count = 0
                self.transcribed.emit(text)
            else:
                if has_voice:
                    self._no_text_count += 1
                    now = time.time()
                    if self._no_text_count >= 3 and (now - self._last_no_text_ts) > 8:
                        self._last_no_text_ts = now
                        hint = ""
                        if not self.groq_api_key:
                            hint = " (No GROQ_API_KEY set; Google STT needs internet access.)"
                        self.error.emit(
                            f"Heard audio but no transcription (rms={rms}, {duration:.1f}s).{hint}"
                        )

    def run(self):
        if sr is None:
            self.error.emit("Voice input unavailable. Install: pip install SpeechRecognition pyaudio")
            return
        try:
            recognizer = sr.Recognizer()
            # 1.2s pause before cutting â€” captures full sentences including mid-thought pauses
            recognizer.pause_threshold = 1.2
            recognizer.non_speaking_duration = 0.4
            recognizer.phrase_threshold = 0.15
            recognizer.dynamic_energy_threshold = True
            candidates, device_names, err = self._get_microphone_candidates()
            if err:
                self.error.emit(err)
                return
            last_err = None
            for device_index in candidates:
                try:
                    with sr.Microphone(
                        device_index=device_index,
                        sample_rate=self.voice_sample_rate,
                        chunk_size=self.voice_chunk_size,
                    ) as source:
                        self._capture_loop(recognizer, source)
                    return
                except Exception as e:
                    last_err = e
                    continue
            if last_err:
                self.error.emit(
                    f"Microphone open failed: {last_err}. Available devices: {', '.join(device_names)}"
                )
            else:
                self.error.emit(
                    f"Microphone open failed. Available devices: {', '.join(device_names)}"
                )
        except Exception as e:
            self.error.emit(f"Voice capture failed: {e}")
