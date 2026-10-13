# Changelog

## 0.1.1

- Clear unconfirmed guesses at the end of capture while retaining confirmed captions.
- Handle audio preparation failures through the local controls.
- Allow a new unsaved capture after opening a saved session.
- Translate runtime labels with the selected interface language.
- Keep caption node references valid when moved to a floating window. Native floating-window behavior still requires browser verification.

## 0.1.0

Initial beta release for local captions on Linux with PulseAudio/PipeWire.

- WhisperLive streaming backend with preloaded Faster Whisper model and CT2 device probing; no additional Torch dependency.
- Local web controls for Whisper base, small and medium, plus an optional Whistle CPU engine.
- System audio, microphone or a temporary combination of both on Linux.
- Local English-to-Spanish translation with CTranslate2 and an Argos package.
- Provisional original text, retained confirmed translation and caption history.
- Technical vocabulary hints and exact term protection during translation.
- Collapsible settings, Spanish/English interface and measured memory guidance per profile.
- Whistle transcription-only CPU profile and named saved sessions with append-only continuation.
- Optional transcript export, application shortcut, publication checks and tests.

Windows/macOS capture, additional translation pairs are not included in this release. Floating-window support depends on the browser and still needs desktop verification. A full fresh installation has not been tested on another machine.
