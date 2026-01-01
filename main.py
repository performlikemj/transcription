# --- macOS dylib workaround: ensure Torch's private libs are discoverable ---
import sys, os, pathlib
if getattr(sys, "frozen", False):  # running inside YardTalk.app
    bundle_root = pathlib.Path(sys.executable).resolve().parents[1]  # .../Contents
    torch_lib_dir = (
        bundle_root
        / "Resources"
        / f"lib/python{sys.version_info.major}.{sys.version_info.minor}"
        / "torch"
        / "lib"
    )
    # Tell the dynamic loader where to look first for @rpath-dependent libs
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = str(torch_lib_dir)
# ---------------------------------------------------------------------------

# Set up file logging for GUI app debugging
import logging
import datetime

# Create a log file in the user's home directory for GUI launches
def _configure_logging():
    log_file = os.path.expanduser("~/Library/Logs/YardTalk/dictation_app.log")
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handlers.insert(0, logging.FileHandler(log_file, mode='w'))
    except Exception as file_error:
        fallback_path = "/tmp/yardtalk.log"
        try:
            handlers.insert(0, logging.FileHandler(fallback_path, mode='w'))
            log_file = fallback_path
        except Exception:
            log_file = None
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=handlers,
        )
        if log_file:
            logging.warning("Logging file handler failed; using fallback path: %s", log_file)
        else:
            logging.warning("Logging file handler failed: %s", file_error)
        return

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers,
    )

_configure_logging()

def log_print(*args, **kwargs):
    """Custom print function that logs to both file and console"""
    message = ' '.join(str(arg) for arg in args)
    logging.info(message)

# Replace print with our logging version
print = log_print

import rumps
from hotkey_manager import HotkeyManager
from audio_manager import AudioManager
from asr_service import ASRService
from text_insertion_service import TextInsertionService
from overlay_window import OverlayWindow
import sounddevice as sd
from PyObjCTools import AppHelper
import time

# Used to distinguish ASR service callbacks
ASR_CALLBACK_TYPE_MODEL_LOAD = "model_load_status"
ASR_CALLBACK_TYPE_TRANSCRIPTION = "transcription_result"

class DictationApp(rumps.App):
    def __init__(self):
        super(DictationApp, self).__init__("Dictation App", icon="icon.png")
        self.menu = ["Toggle Dictation", "Settings", None, "Quit"]
        
        self.dictation_active = False
        self.is_transcribing = False 
        # Use a hotkey combination that doesn't conflict with common system shortcuts
        self.hotkey_string = "<cmd>+<shift>+d"  # Command+Shift+D - less likely to conflict
        
        self.asr_model_status = "initializing" # "initializing", "loaded", "error"
        # Flag to ensure MODEL_LOADED_SUCCESSFULLY is handled only once
        self._model_loaded_handled = False
        self.active_timers = [] # Add a list to keep track of active timers
        self._last_transcribed_text = None  # Remember the last text we actually typed
        self.update_menu_state()
        self._debug_id_counter = 0 # For generating unique log IDs

        # Initialize services
        self.audio_manager = AudioManager()
        self.text_insertion_service = TextInsertionService()
        self.overlay_window = OverlayWindow()

        # Determine model path based on whether we're running from a bundle or source
        if getattr(sys, "frozen", False):
            # Running inside YardTalk.app
            bundle_root = pathlib.Path(sys.executable).resolve().parents[1]  # .../Contents
            model_path = bundle_root / "Resources" / "parakeet-tdt-0.6b-v2" / "parakeet-tdt-0.6b-v2.nemo"
            model_path = str(model_path)
        else:
            # Running from source
            model_path = "parakeet-tdt-0.6b-v2/parakeet-tdt-0.6b-v2.nemo"
        
        print(f"MAIN_APP: Using model path: {model_path}")
        self.asr_service = ASRService(model_path=model_path, result_callback=self._handle_asr_service_result)
        
        # Initialize hotkey manager but don't start it yet
        self.hotkey_manager = HotkeyManager(
            hotkey_str=self.hotkey_string,
            on_activate=self.request_activate_dictation,
            on_deactivate=self.request_deactivate_dictation
        )
        
        # Start hotkey manager after a short delay to ensure rumps is fully initialized
        print("MAIN_APP: Scheduling hotkey manager startup...")
        rumps.Timer(self._start_hotkey_manager, 1.0).start()
        
        # Initial menu state is set above, will be updated by ASR callback

    def _start_hotkey_manager(self, timer):
        """Start the hotkey manager after rumps is fully initialized"""
        print("MAIN_APP: Starting hotkey manager...")
        try:
            self.hotkey_manager.start_listening()
            print(f"MAIN_APP: Hotkey manager started successfully for {self.hotkey_string}")
            rumps.notification("Dictation App", "Hotkeys Active", f"Press {self.hotkey_string} to start dictation")
        except Exception as e:
            print(f"MAIN_APP: Failed to start hotkey manager: {e}")
            rumps.alert("Hotkey Error", f"Failed to start hotkey listener: {e}")
        finally:
            timer.stop()  # Make this a one-shot timer

    def _process_audio_chunk(self, chunk):
        self.asr_service.process_audio_chunk(chunk)
        if self.overlay_window:
            self.overlay_window.add_chunk(chunk)

    def _create_timer_on_main(self, payload_with_context):
        # payload_with_context is expected to be timer_payload_for_main_thread from _handle_asr_service_result
        # Let's assume it might contain a 'log_id' if we pass it from _handle_asr_service_result
        log_id_for_timer = payload_with_context.pop('log_id_for_timer', f"timer_{time.monotonic()}")

        # This method is called on the main thread via performSelectorOnMainThread_
        print(f"MAIN_APP ({log_id_for_timer}): _create_timer_on_main executing on main thread.")
        timer_instance = rumps.Timer(self._process_asr_result_on_main_thread, 0.0)
        timer_instance.user_payload = payload_with_context # This is the original timer_payload_for_main_thread
        timer_instance.log_id = log_id_for_timer # Attach log_id to timer instance
        
        if not hasattr(self, 'active_timers'):
            self.active_timers = []
        self.active_timers.append(timer_instance)
        timer_instance.start()
        print(f"MAIN_APP ({log_id_for_timer}): Timer started for _process_asr_result_on_main_thread.")

    def _handle_asr_service_result(self, result_payload, error_payload):
        # Generate a log ID for this specific ASR result handling sequence
        asr_result_log_id = f"asr_res_{time.monotonic()}"
        print(f"MAIN_APP ({asr_result_log_id}): _handle_asr_service_result ENTERED. Result: '{str(result_payload)[:50]}...', Error: {error_payload}")

        if result_payload == "MODEL_LOADED_SUCCESSFULLY" and self._model_loaded_handled:
            print(f"MAIN_APP ({asr_result_log_id}): Duplicate MODEL_LOADED_SUCCESSFULLY received, ignoring.")
            return
        
        callback_type = ASR_CALLBACK_TYPE_TRANSCRIPTION 
        data_to_pass = {'text': result_payload, 'error': error_payload}

        if result_payload == "MODEL_LOADED_SUCCESSFULLY":
            callback_type = ASR_CALLBACK_TYPE_MODEL_LOAD
            data_to_pass = {'status': "loaded", 'error': None}
            self._model_loaded_handled = True
            print(f"MAIN_APP ({asr_result_log_id}): Processed as MODEL_LOADED_SUCCESSFULLY.")
        elif error_payload and self.asr_model_status == "initializing": 
            callback_type = ASR_CALLBACK_TYPE_MODEL_LOAD
            data_to_pass = {'status': "error", 'error': error_payload}
            print(f"MAIN_APP ({asr_result_log_id}): Processed as MODEL_LOAD error during init.")
        elif callback_type == ASR_CALLBACK_TYPE_TRANSCRIPTION:
            # Fix 2: Don't even create a timer for blank results
            if error_payload is None and (
                result_payload is None
                or (isinstance(result_payload, str) and result_payload.strip() == "")
            ):
                print(f"MAIN_APP ({asr_result_log_id}): Empty or blank transcription received from ASRService. Skipping timer creation.")
                # Explicitly set is_transcribing to False here if appropriate, 
                # as _process_asr_result_on_main_thread won't be called to do it.
                if self.is_transcribing: # Only if we were actually waiting for a transcription
                    self.is_transcribing = False
                    print(f"MAIN_APP ({asr_result_log_id}): Set is_transcribing to False due to blank result.")
                    # Potentially reset hotkey_manager.hotkey_active as well, like in _process_asr_result_on_main_thread finally block
                    if self.hotkey_manager.hotkey_active:
                        print(f"MAIN_APP ({asr_result_log_id}): Resetting hotkey_manager.hotkey_active from True to False (blank result).")
                        self.hotkey_manager.hotkey_active = False
                    self.update_menu_state()
                return
        
        timer_payload_for_main_thread = {'type': callback_type, 'data': data_to_pass}
        
        # Pass the asr_result_log_id to be used by _create_timer_on_main
        payload_with_context = timer_payload_for_main_thread.copy() # Avoid modifying original dict if it's used elsewhere
        payload_with_context['log_id_for_timer'] = asr_result_log_id

        print(f"MAIN_APP ({asr_result_log_id}): Posting to _create_timer_on_main via AppHelper.callAfter.")
        AppHelper.callAfter(self._create_timer_on_main, payload_with_context)
        print(f"MAIN_APP ({asr_result_log_id}): _handle_asr_service_result EXITED.")

    def _process_asr_result_on_main_thread(self, timer_instance): # Receives the Timer instance
        log_id = hasattr(timer_instance, 'log_id') and timer_instance.log_id or "unknown_timer"
        print(f"MAIN_APP ({log_id}): _process_asr_result_on_main_thread ENTERED.")
        try:
            # This runs on the main Rumps thread
            user_payload = timer_instance.user_payload
            callback_type = user_payload['type']
            data = user_payload['data']

            if callback_type == ASR_CALLBACK_TYPE_MODEL_LOAD:
                status = data['status']
                error = data['error']
                if status == "loaded":
                    self.asr_model_status = "loaded"
                    rumps.notification("Dictation App", "Ready", f"ASR model loaded. Press {self.hotkey_string} to dictate.")
                elif status == "error":
                    self.asr_model_status = "error"
                    rumps.alert("ASR Model Error", f"Failed to load ASR model: {str(error)}. Transcription will not be available.")
            
            elif callback_type == ASR_CALLBACK_TYPE_TRANSCRIPTION:
                transcribed_text = data['text']
                error_obj = data['error'] # Renamed to avoid conflict with 'error' in MODEL_LOAD

                # Existing handling for actual transcription results
                try:
                    if error_obj:
                        rumps.alert("Transcription Failed", f"Could not transcribe audio: {str(error_obj)}")
                        return
                    # Fix 1 (part 1): Bail out early on empty text
                    # This check is now also in _handle_asr_service_result, but good to have defensively here too.
                    if transcribed_text is None or (isinstance(transcribed_text, str) and transcribed_text.strip() == ""):
                        print(f"MAIN_APP ({log_id}): Transcription result is None or blank. Bailing out early from processing.")
                        # No notification for blank text here, as it's handled by _handle_asr_service_result or if it slips through.
                        return # Return directly from here. The finally block will still execute.
                    elif transcribed_text is not None: # We already checked for blank, so this means non-blank
                        if transcribed_text == self._last_transcribed_text:
                            pass 
                        else:
                            print("--- Transcribed Text ---")
                            print(transcribed_text)
                            print("------------------------")
                            try:
                                print(f"MAIN_APP ({log_id}): Attempting to insert text...")
                                insertion_result = self.text_insertion_service.insert_text(transcribed_text)
                                print(f"MAIN_APP ({log_id}): Text insertion result: {insertion_result}")
                                if insertion_result:
                                    rumps.notification("Transcription Complete", "Text inserted.", transcribed_text)
                                else:
                                    rumps.notification("Insertion Failed", "Could not type text.", transcribed_text)
                                    rumps.alert("Transcription (Insertion Failed)", transcribed_text)
                            except Exception as insertion_error:
                                print(f"MAIN_APP ({log_id}): ERROR during text insertion: {insertion_error}")
                                import traceback
                                traceback.print_exc()
                                rumps.notification("Insertion Error", f"Text insertion crashed: {str(insertion_error)}", transcribed_text)
                                rumps.alert("Transcription (Insertion Error)", f"Error: {str(insertion_error)}\n\nText: {transcribed_text}")
                            self._last_transcribed_text = transcribed_text
                    # No explicit 'else' for transcribed_text == "" here as we return early if blank
                finally:
                    # This 'finally' is for the inner try related to processing transcription text and errors.
                    # The main state flags (is_transcribing, dictation_active) are reset in the outer finally block.
                    pass # Placeholder, could remove this inner finally if not strictly needed
        except Exception as e_outer:
            print(f"MAIN_APP ({log_id}): CRITICAL ERROR in _process_asr_result_on_main_thread: {e_outer}")
            import traceback
            traceback.print_exc()
        finally:
            # Fix 1 (part 2): Make this timer truly one-shot
            print(f"MAIN_APP ({log_id}): Stopping and removing timer.")
            timer_instance.stop()
            if timer_instance in self.active_timers:
                self.active_timers.remove(timer_instance)
            else:
                print(f"MAIN_APP ({log_id}): Timer was not in active_timers list for removal.")

            # This is the outer finally, ensure state flags are reset here if a transcription was processed (or attempted)
            # Only reset these if it was a transcription callback, not a model_load callback.
            if callback_type == ASR_CALLBACK_TYPE_TRANSCRIPTION:
                print(f"MAIN_APP ({log_id}): Outer FINALLY for ASR_CALLBACK_TYPE_TRANSCRIPTION. is_transcribing PRE: {self.is_transcribing}, dictation_active PRE: {self.dictation_active}")
                self.is_transcribing = False 
                self.dictation_active = False
                
                current_hotkey_active_state = self.hotkey_manager.hotkey_active
                print(f"MAIN_APP ({log_id}): Hotkey_manager.hotkey_active PRE-check: {current_hotkey_active_state}")
                if self.hotkey_manager.hotkey_active:
                    print(f"MAIN_APP ({log_id}): Resetting hotkey_manager.hotkey_active from True to False.")
                    self.hotkey_manager.hotkey_active = False
                
                audio_is_recording_flag = getattr(self.audio_manager, "_is_recording", "N/A")
                print(f"MAIN_APP ({log_id}): AudioManager._is_recording PRE-check: {audio_is_recording_flag}")
                if audio_is_recording_flag == True:
                    print(f"MAIN_APP ({log_id}): Cleanup – mic was still flagged recording; stopping.")
                    self.audio_manager.stop_recording(f"from_process_asr_result_finally_{log_id}")
                    if self.overlay_window:
                        AppHelper.callAfter(self.overlay_window.hide)
                
                print(f"MAIN_APP ({log_id}): is_transcribing POST: {self.is_transcribing}, dictation_active POST: {self.dictation_active}")
            else:
                print(f"MAIN_APP ({log_id}): Outer FINALLY for {callback_type}. Not resetting transcription-specific flags.")

            self.update_menu_state()

    def request_activate_dictation(self):
        AppHelper.callAfter(self._activate_dictation_main)

    def _activate_dictation_main(self):
        self._debug_id_counter += 1
        log_id = f"activate_{self._debug_id_counter}"
        print(f"MAIN_APP ({log_id}): _activate_dictation_main ENTERED.")
        
        # Directive B: Stop-before-restart guard
        audio_is_recording_flag = getattr(self.audio_manager, "_is_recording", "N/A")
        print(f"MAIN_APP ({log_id}): Directive B check: audio_manager._is_recording = {audio_is_recording_flag}")
        if audio_is_recording_flag == True: # Explicitly check True
            rumps.notification("Mic busy", "Still closing the previous stream…", "")
            if self.hotkey_manager.hotkey_active: 
                self.hotkey_manager.hotkey_active = False
            print(f"MAIN_APP ({log_id}): Mic busy, returning.")
            return

        print(f"MAIN_APP ({log_id}): State pre-activation: asr_model_status='{self.asr_model_status}', is_transcribing={self.is_transcribing}, dictation_active={self.dictation_active}")

        if self.asr_model_status == "initializing":
            rumps.notification("ASR Not Ready", "Model is still initializing.", "Please wait.")
            if self.hotkey_manager.hotkey_active: self.hotkey_manager.hotkey_active = False
            print(f"MAIN_APP ({log_id}): ASR initializing, returning.")
            return
        if self.asr_model_status == "error":
            rumps.alert("ASR Error", "ASR model failed to load. Cannot start dictation.")
            if self.hotkey_manager.hotkey_active: self.hotkey_manager.hotkey_active = False
            return
        if self.is_transcribing:
            print(f"MAIN_APP ({log_id}): Already transcribing, returning.")
            return

        if not self.dictation_active:
            print(f"MAIN_APP ({log_id}): Activation - Starting dictation logic...")
            print(f"MAIN_APP ({log_id}): Activation - Before clearing ASR buffer.")
            self.asr_service.get_buffered_audio_and_clear() # Clear any old audio
            print(f"MAIN_APP ({log_id}): Activation - After clearing ASR buffer.")
            
            self.dictation_active = True
            print(f"MAIN_APP ({log_id}): dictation_active SET to True.")
            if self.overlay_window:
                self.overlay_window.show()  # Call directly - we're already on main thread
            self.audio_manager.set_chunk_callback(self._process_audio_chunk)
            print(f"MAIN_APP ({log_id}): Calling audio_manager.start_recording().")
            if self.audio_manager.start_recording(f"from_activate_{log_id}"):
                rumps.notification("Dictation Started", "Listening...", "Press hotkey again to stop.")
            else:
                print(f"MAIN_APP ({log_id}): Activation - Failed to start audio recording.")
                error_detail = None
                if hasattr(self.audio_manager, "get_last_error"):
                    error_detail = self.audio_manager.get_last_error()
                error_message = "Failed to start audio recording."
                if error_detail:
                    error_text = str(error_detail)
                    error_message = f"{error_message}\n\n{error_text}"
                    if any(keyword in error_text.lower() for keyword in ("permission", "not permitted", "denied")):
                        error_message = (
                            f"{error_message}\n\n"
                            "Check System Settings > Privacy & Security > Microphone and allow YardTalk."
                        )
                rumps.alert("Audio Error", error_message)
                self.dictation_active = False
                if self.hotkey_manager.hotkey_active: self.hotkey_manager.hotkey_active = False
            self.update_menu_state()

    def request_deactivate_dictation(self):
        self._debug_id_counter += 1
        log_id = f"deactivate_req_{self._debug_id_counter}"
        print(f"MAIN_APP ({log_id}): request_deactivate_dictation called.")
        AppHelper.callAfter(self._deactivate_dictation_main)

    def _deactivate_dictation_main(self):
        # Note: log_id for _deactivate_dictation_main will be from the request_... call context if needed,
        # or we can generate one if it's called directly (though it shouldn't be).
        # For now, let's assume AppHelper carries context or we manage within.
        # For simplicity, use a new counter for direct calls to _deactivate_dictation_main if any.
        # However, it's always called via AppHelper.callAfter(self._deactivate_dictation_main)
        # which doesn't easily pass the log_id. Let's create one here.
        # This might lead to the counter being less sequential across activate/deactivate if they interleave rapidly.
        # A shared counter or passing log_id through AppHelper might be better if strict sequence is vital.
        # For now, a local log_id for this function's scope:
        # Let's use a timestamp for deactivate log_id to make it unique
        import time
        log_id = f"deactivate_main_{time.monotonic()}"

        print(f"MAIN_APP ({log_id}): _deactivate_dictation_main ENTERED.")
        print(f"MAIN_APP ({log_id}): State pre-deactivation: dictation_active={self.dictation_active}, is_transcribing={self.is_transcribing}")

        if not self.dictation_active:
            print(f"MAIN_APP ({log_id}): Deactivation called when dictation_active was False.")
            audio_is_recording_flag = getattr(self.audio_manager, "_is_recording", "N/A")
            print(f"MAIN_APP ({log_id}): audio_manager._is_recording = {audio_is_recording_flag}")
            if audio_is_recording_flag == True: # Explicitly check True
                print(f"MAIN_APP ({log_id}): AudioManager was unexpectedly recording. Stopping it now.")
                self.audio_manager.stop_recording(f"from_deactivate_not_active_{log_id}")
            
            if not self.is_transcribing:
                 if self.hotkey_manager.hotkey_active:
                    print(f"MAIN_APP ({log_id}): Resetting hotkey_active state (deactivation while not active/transcribing).")
                    self.hotkey_manager.hotkey_active = False
            else: # Not dictation_active, but is_transcribing
                print(f"MAIN_APP ({log_id}): Deactivation while not dictation_active, but is_transcribing. Hotkey likely to be reset by ASR callback.")

            self.update_menu_state() 
            print(f"MAIN_APP ({log_id}): _deactivate_dictation_main EXITED (dictation not active path).")
            return

        print(f"MAIN_APP ({log_id}): Deactivation - Stopping dictation logic...")
        self.dictation_active = False
        print(f"MAIN_APP ({log_id}): dictation_active SET to False.")
        print(f"MAIN_APP ({log_id}): Calling audio_manager.stop_recording().")
        self.audio_manager.stop_recording(f"from_deactivate_active_{log_id}")
        if self.overlay_window:
            AppHelper.callAfter(self.overlay_window.hide)
        print(f"MAIN_APP ({log_id}): Audio recording stopped call returned.")

        if self.is_transcribing:
            print(f"MAIN_APP ({log_id}): Deactivation - Transcription already in progress. Ignoring duplicate ASR submit request.")
            self.update_menu_state()
            print(f"MAIN_APP ({log_id}): _deactivate_dictation_main EXITED (already transcribing path).")
            return

        print(f"MAIN_APP ({log_id}): Getting buffered audio from ASR service.")
        audio_to_transcribe = self.asr_service.get_buffered_audio_and_clear()
        if audio_to_transcribe.size == 0:
            print(f"MAIN_APP ({log_id}): Deactivation - Audio buffer is empty. Nothing to transcribe.")
            rumps.notification("Dictation Stopped", "No audio recorded.", "")
            # If nothing to transcribe, ensure hotkey_active is False if it was True from the deactivation press
            if self.hotkey_manager.hotkey_active:
                 print(f"MAIN_APP ({log_id}): No audio, ensuring hotkey_manager.hotkey_active is False.")
                 self.hotkey_manager.hotkey_active = False
            self.update_menu_state()
            print(f"MAIN_APP ({log_id}): _deactivate_dictation_main EXITED (no audio to transcribe path).")
            return

        print(f"MAIN_APP ({log_id}): Submitting {len(audio_to_transcribe)} audio samples for transcription.")
        self.is_transcribing = True
        print(f"MAIN_APP ({log_id}): is_transcribing SET to True.")
        # Generate a log_id for this transcription request to track it into the callback
        transcription_log_id = f"asr_req_{time.monotonic()}"
        print(f"MAIN_APP ({log_id}): Submitting to ASR with transcription_log_id: {transcription_log_id}")
        # How to pass transcription_log_id to _handle_asr_service_result?
        # ASRService callback doesn't directly support passing extra context this way.
        # For now, the timer_instance in _create_timer_on_main will get its own ID.
        # We can correlate by timestamps in logs.
        # Let's try to attach it to the timer payload.
        
        # Modify _create_timer_on_main and _handle_asr_service_result to carry this ID.
        # This means the current edit is insufficient alone.
        # For now, just submit. The next step will be to modify the timer logic.
        self.asr_service.submit_transcription_request(audio_to_transcribe) 
        
        rumps.notification("Dictation Stopped", "Processing audio...", "Please wait.")
        self.update_menu_state()
        print(f"MAIN_APP ({log_id}): _deactivate_dictation_main EXITED (submitted to ASR path).")

    def update_menu_state(self):
        toggle_item = self.menu["Toggle Dictation"]
        
        current_title = "Dictation App"
        menu_item_title = f"Start Dictation (Press {self.hotkey_string})"

        if self.asr_model_status == "initializing":
            current_title = "Dictation App (ASR Init...)"
            menu_item_title = "ASR Initializing..."
        elif self.asr_model_status == "error":
            current_title = "Dictation App (ASR ERR)"
            menu_item_title = "ASR Model Failed"
        elif self.is_transcribing:
            current_title = "Dictation App (Processing...)"
            menu_item_title = "Processing..."
        elif self.dictation_active:
            current_title = "Dictation App (Rec ●)"
            menu_item_title = "Stop Dictation (Rec ●)"
        
        if self.title != current_title:
            self.title = current_title
        if toggle_item and toggle_item.title != menu_item_title:
            toggle_item.title = menu_item_title

    @rumps.clicked("Toggle Dictation")
    def toggle_dictation_manual(self, _):
        """Manual toggle for dictation - useful when hotkeys aren't working"""
        print("MAIN_APP: Manual toggle dictation clicked")
        
        if self.asr_model_status == "initializing":
            rumps.notification("ASR Not Ready", "Model is still initializing.", "Please wait.")
            return
        elif self.asr_model_status == "error":
            rumps.alert("ASR Error", "ASR model failed to load. Cannot start dictation.")
            return
        
        if self.dictation_active:
            # Currently active, so deactivate
            self.request_deactivate_dictation()
        else:
            # Currently inactive, so activate
            self.request_activate_dictation()

    @rumps.clicked("Settings")
    def settings(self, _):
        mic_names = []
        try:
            devices = sd.query_devices()
            input_devices = [dev for dev in devices if dev['max_input_channels'] > 0]
            for i, device in enumerate(input_devices):
                mic_names.append(f"{i}: {device['name']}")
            mic_info = "\nAvailable Microphones:\n" + "\n".join(mic_names) if mic_names else "\nNo microphones found."
        except Exception as e:
            mic_info = f"\nCould not query microphones: {e}"

        asr_status_detail = "Unknown"
        if self.asr_model_status == "loaded":
            asr_status_detail = f"Loaded on {self.asr_service.device if self.asr_service else 'N/A'}"
        elif self.asr_model_status == "initializing":
            asr_status_detail = "Initializing..."
        elif self.asr_model_status == "error":
            asr_status_detail = "Error during load"
        
        settings_message = f"Hotkey: {self.hotkey_string}\nASR Model Status: {asr_status_detail}{mic_info}"
        rumps.alert("Settings", settings_message)

    @rumps.clicked("Quit")
    def quit_app(self, _):
        print("MAIN_APP: Quit clicked.")
        if self.dictation_active:
            print("MAIN_APP: Quit - Dictation was active, stopping audio manager...")
            self.audio_manager.stop_recording()
            if self.overlay_window:
                self.overlay_window.hide()
        
        print("MAIN_APP: Quit - Shutting down ASR service...")
        if self.asr_service: # Check if ASR service was initialized
            self.asr_service.shutdown() # Signal worker thread to stop
        
        print("MAIN_APP: Quit - Stopping hotkey manager.")
        if self.hotkey_manager: # Check if hotkey manager was initialized
            self.hotkey_manager.stop_listening()
        
        rumps.quit_application()

if __name__ == "__main__":
    # This dummy icon creation should ideally be conditional or handled better.
    try:
        with open("icon.png", "rb") as f:
            pass # Icon exists
    except FileNotFoundError:
        try:
            import base64
            png_data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
            with open("icon.png", "wb") as f:
                f.write(png_data)
            print("Created dummy icon.png for main.py")
        except Exception as e:
            print(f"Could not create dummy icon.png for main.py: {e}")
            
    app = DictationApp()
    app.run() 
