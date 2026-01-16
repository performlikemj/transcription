import nemo.collections.asr as nemo_asr
import numpy as np
import torch # NeMo models are PyTorch based
import os
import queue
import threading
import time # Ensure time is imported at the top
import logging

# Set up logging for ASR service
logger = logging.getLogger('ASRService')

def log_print(*args, **kwargs):
    """Custom print function that logs to file"""
    message = ' '.join(str(arg) for arg in args)
    logger.info(message)
    # Also print to console
    import builtins
    builtins.print(*args, **kwargs)

# Replace print with our logging version
print = log_print

# Sentinel object for signaling shutdown
SHUTDOWN_SENTINEL = object()

class ASRService:
    def __init__(self, model_path=None, result_callback=None):
        self.model_path = model_path
        self.asr_model = None
        self.device = None
        self._buffer = [] # To accumulate audio chunks for transcription
        self.is_model_loaded = False
        self.result_callback = result_callback # Callback to send transcription results to
        self.greedy_decoder = None # For RNNT state reset

        self.request_queue = queue.Queue()
        self._asr_worker_thread = threading.Thread(target=self._asr_worker_loop)
        self._asr_worker_thread.daemon = True
        self._asr_worker_thread.start()

    def _initialize_model_on_worker(self):
        # This method is called by the ASR worker thread
        print("ASR_SERVICE (worker): Initializing ASR model...")
        if not self.model_path or not os.path.exists(self.model_path):
            error_msg = "No model path specified" if not self.model_path else f"Model file not found: {self.model_path}"
            print(f"ASR_SERVICE (worker): ERROR - {error_msg}")
            if self.result_callback:
                self.result_callback(None, FileNotFoundError(error_msg))
            return False

        if torch.backends.mps.is_available() and torch.backends.mps.is_built():
            self.device = torch.device("mps")
            print("ASR_SERVICE (worker): Using MPS device (Apple Silicon GPU).")
        elif torch.cuda.is_available():
            self.device = torch.device("cuda")
            print("ASR_SERVICE (worker): Using CUDA device.")
        else:
            self.device = torch.device("cpu")
            print("ASR_SERVICE (worker): Using CPU device.")

        try:
            self.asr_model = nemo_asr.models.EncDecRNNTBPEModel.restore_from(self.model_path, map_location=self.device)
            self.asr_model.eval()
            
            # Attempt to get the greedy decoder for RNNT reset, if applicable
            if hasattr(self.asr_model, 'decoding') and hasattr(self.asr_model.decoding, 'reset'):
                self.greedy_decoder = self.asr_model.decoding
                print("ASR_SERVICE (worker): Acquired greedy_decoder for potential RNNT state reset.")
            else:
                # This could be a CTC model, or an RNNT model where .decoding isn't structured as expected.
                # If it's truly Parakeet-TDT (RNNT), and this path is taken, reset won't happen as prescribed.
                print("ASR_SERVICE (worker): NOTE - self.asr_model.decoding.reset not found. State reset for RNNT might not be configured as expected.")

            self.is_model_loaded = True
            print(f"ASR_SERVICE (worker): Model '{type(self.asr_model).__name__}' loaded on {self.device}.")
            
            # Warm-up call
            with torch.no_grad():
                dummy_input = np.zeros(16000, dtype=np.float32)
                self.asr_model.transcribe([dummy_input], batch_size=1)
            print("ASR_SERVICE (worker): Model warmed up.")
            if self.result_callback: # Signal successful load
                print(f"ASR_SERVICE (worker): Calling result_callback for MODEL_LOADED_SUCCESSFULLY. Callback: {self.result_callback}") # Diagnostic print
                self.result_callback("MODEL_LOADED_SUCCESSFULLY", None)
            return True
        except Exception as e:
            print(f"ASR_SERVICE (worker): ERROR loading ASR model: {e}")
            self.asr_model = None
            self.is_model_loaded = False
            if self.result_callback:
                self.result_callback(None, e) # Send error back
            return False

    def _reset_decoder_state_on_worker(self):
        if self.greedy_decoder:
            try:
                self.greedy_decoder.reset()
                print("ASR_SERVICE (worker): RNNT decoder state reset.")
            except Exception as e:
                print(f"ASR_SERVICE (worker): ERROR attempting to reset RNNT decoder state: {e}")
        # If greedy_decoder is None, it means it wasn't applicable or found, so we do nothing.

    def _perform_transcription_on_worker(self, audio_data_np):
        if not self.is_model_loaded or self.asr_model is None:
            print("ASR_SERVICE (worker): Model not loaded, cannot transcribe.")
            return None, RuntimeError("ASR model not loaded")

        if audio_data_np.size == 0:
            print("ASR_SERVICE (worker): Cannot transcribe empty audio.")
            return "", None # Empty string, no error for empty audio

        print(f"ASR_SERVICE (worker): Transcribing audio of length {len(audio_data_np)} samples.")

        # Audio diagnostics
        audio_max = np.max(np.abs(audio_data_np))
        audio_mean = np.mean(np.abs(audio_data_np))
        audio_rms = np.sqrt(np.mean(audio_data_np**2))
        print(f"ASR_SERVICE (worker): Audio stats - max: {audio_max:.6f}, mean: {audio_mean:.6f}, RMS: {audio_rms:.6f}")
        if audio_max < 0.01:
            print("ASR_SERVICE (worker): WARNING - Audio level very low! May be silence or microphone not working.")

        transcribed_text = "" # Default to empty string
        try:
            with torch.no_grad():
                # Actual transcription
                print(f"ASR_SERVICE (worker): Transcribing audio data of shape: {audio_data_np.shape}, dtype: {audio_data_np.dtype}")
                try:
                    # 1) Fast path for recent checkpoints (decoding.reset exists)
                    if hasattr(self.asr_model, "decoding") and hasattr(self.asr_model.decoding, "reset"):
                        self.asr_model.decoding.reset()
                        print("ASR_SERVICE (worker): Decoder reset via decoding.reset().")

                    # 2) Fallback – recreate the decoder from config
                    elif hasattr(self.asr_model, "change_decoding_strategy"):
                        # Re-build the default greedy decoder described by self.asr_model.cfg.decoding
                        self.asr_model.change_decoding_strategy(self.asr_model.cfg.decoding)
                        print("ASR_SERVICE (worker): Decoder rebuilt via change_decoding_strategy().")

                    # 3) As a last resort, nuke any cached state on the decoder object
                    elif hasattr(self.asr_model, "decoder") and hasattr(self.asr_model.decoder, "decoder_state"):
                        self.asr_model.decoder.decoder_state = None
                        print("ASR_SERVICE (worker): Decoder_state set to None (best-effort reset).")

                    else:
                        print("ASR_SERVICE (worker): WARNING – no safe way to reset decoder; results may repeat.")
                except Exception as e:
                    print(f"ASR_SERVICE (worker): Decoder-reset step threw: {e}")
                transcription_results = self.asr_model.transcribe([audio_data_np], batch_size=1)

                # Process results: NeMo models usually return a list of transcriptions.
                # For batch_size=1, it's a list with one item.
                # This item can be a string or a hypothesis object.
                if transcription_results and len(transcription_results) > 0:
                    result = transcription_results[0]
                    if isinstance(result, str):
                        transcribed_text = result.strip()
                    elif hasattr(result, 'text'):  # Common for hypothesis objects
                        transcribed_text = result.text
                    elif isinstance(result, list) and len(result) > 0 and hasattr(result[0], 'text'): # List of hypotheses
                        transcribed_text = result[0].text
                    elif isinstance(result, list) and len(result) > 0 and isinstance(result[0], str): # List of strings
                        transcribed_text = result[0]
                    else:
                        print(f"ASR_SERVICE (worker): Unexpected transcription result format: {type(result)}. Content: {result}")
                        transcribed_text = "" # Fallback
                else:
                    print("ASR_SERVICE (worker): Transcription returned no or empty results.")
                    transcribed_text = ""

                print(f"ASR_SERVICE (worker): Raw transcription: '{transcribed_text}'")

            return transcribed_text, None
        except Exception as e:
            print(f"ASR_SERVICE (worker): ERROR during transcription: {e}")
            return None, e

    def _asr_worker_loop(self):
        print("ASR_SERVICE: ASR worker thread started.")
        if not self._initialize_model_on_worker():
            print("ASR_SERVICE: Failed to initialize model in worker thread. Worker exiting.")
            return

        while True:
            try:
                request = self.request_queue.get() # Blocks until an item is available

                if request is SHUTDOWN_SENTINEL:
                    print("ASR_SERVICE (worker): Shutdown signal received. Exiting loop.")
                    break
                
                audio_data_np = request # Assuming request is the numpy audio array
                transcribed_text, error = self._perform_transcription_on_worker(audio_data_np)
                
                if self.result_callback:
                    self.result_callback(transcribed_text, error)
                
                self.request_queue.task_done() # Signal that the task is done

            except Exception as e:
                # This is a safety net for unexpected errors in the worker loop itself.
                print(f"ASR_SERVICE (worker): UNEXPECTED ERROR in worker loop: {e}")
                if self.result_callback:
                    # Send a generic error back if something goes wrong with the loop/queue handling
                    self.result_callback(None, e)
                # Consider if we should break or continue after such an error.
                # For now, let's continue, but this might need review.
                if not isinstance(request, np.ndarray): # If the request itself was bad, mark as done
                    self.request_queue.task_done()

        print("ASR_SERVICE: ASR worker thread finished.")

    def process_audio_chunk(self, chunk_int16):
        if not self.is_model_loaded and not self._asr_worker_thread.is_alive():
            # This case might happen if model loading failed and worker exited early
            print("ASR_SERVICE: Model not loaded or worker not running, cannot process audio.")
            return

        chunk_float32 = chunk_int16.astype(np.float32) / 32768.0
        if chunk_float32.ndim > 1 and chunk_float32.shape[1] == 1:
            chunk_float32 = chunk_float32.flatten()
        self._buffer.append(chunk_float32)

    def get_buffered_audio_and_clear(self):
        buffered_item_count = len(self._buffer)
        approx_samples = 0
        if buffered_item_count > 0:
            try:
                approx_samples = sum(len(c) for c in self._buffer if hasattr(c, '__len__'))
            except TypeError: # If items in buffer are not iterable or len() not applicable
                approx_samples = -1 # Indicate an issue with buffer contents
        print(f"ASR_SERVICE: get_buffered_audio_and_clear called. Buffer items before clear: {buffered_item_count}, Approx samples: {approx_samples}")
        
        if not self._buffer:
            # print("ASR_SERVICE: Buffer is empty, returning empty array.")
            return np.array([], dtype=np.float32)
        
        try:
            full_audio = np.concatenate(self._buffer)
        except ValueError as e:
            print(f"ASR_SERVICE: ERROR concatenating audio buffer: {e}. Buffer contents might be inconsistent. Clearing and returning empty.")
            self._buffer = []
            return np.array([], dtype=np.float32)
            
        self._buffer = []
        print("ASR_SERVICE: Buffer cleared. Returning concatenated audio.")
        return full_audio

    def submit_transcription_request(self, audio_data_np):
        if not self._asr_worker_thread.is_alive():
            print("ASR_SERVICE: Worker thread is not alive. Cannot submit request.")
            if self.result_callback:
                self.result_callback(None, RuntimeError("ASR worker not available."))
            return
        # Do not check self.is_model_loaded here; requests can be queued even if model is still loading.
        # The worker will handle it or return an error if it tries to use a non-loaded model.
        print(f"ASR_SERVICE: Submitting audio for transcription (length: {len(audio_data_np)} samples).")
        self.request_queue.put(audio_data_np)

    def shutdown(self):
        print("ASR_SERVICE: Initiating shutdown of ASR worker thread...")
        if self._asr_worker_thread.is_alive():
            self.request_queue.put(SHUTDOWN_SENTINEL)
            self._asr_worker_thread.join(timeout=5.0) # Wait for thread to exit
            if self._asr_worker_thread.is_alive():
                print("ASR_SERVICE: WARNING - ASR worker thread did not shut down cleanly.")
            else:
                print("ASR_SERVICE: ASR worker thread shut down successfully.")
        else:
            print("ASR_SERVICE: ASR worker thread was not alive at shutdown.")

if __name__ == '__main__':
    # Test for the ASRService with worker thread
    print("Testing ASRService with worker thread...")

    # Dummy callback for testing
    def test_result_callback(text, error):
        print("--- TEST CALLBACK RECEIVED ---")
        if error:
            print(f"Error: {error}")
        else:
            print(f"Transcription: '{text}'")
        print("-----------------------------")

    asr_service = ASRService(result_callback=test_result_callback)

    print("Main thread: Waiting for model to load (up to 30s)...")
    initialization_timeout = 30 
    wait_interval = 0.5
    # Wait for the special "MODEL_LOADED_SUCCESSFULLY" signal or timeout or error
    # This requires the callback to be sophisticated enough or use a shared event.
    # For this test, we'll check is_model_loaded, but callback is prime for real app.
    model_ready = False
    original_callback = asr_service.result_callback # Save original for testing
    
    # Temp callback to detect model load for test purposes
    model_load_event = threading.Event()
    def _test_model_load_callback(text, error):
        if text == "MODEL_LOADED_SUCCESSFULLY":
            print("--- TEST: Model loaded successfully signal received by callback ---")
            model_load_event.set()
        elif error and isinstance(error, FileNotFoundError):
            print(f"--- TEST: Model file not found error received by callback: {error} ---")
            model_load_event.set() # Signal to stop waiting
        elif error:
            print(f"--- TEST: Generic error during init received by callback: {error} ---")
            model_load_event.set() # Signal to stop waiting
        # Call original callback too if needed for other test messages
        if original_callback and not (text == "MODEL_LOADED_SUCCESSFULLY" or error):
             original_callback(text,error)

    asr_service.result_callback = _test_model_load_callback

    print(f"Main thread: Waiting for model load signal via callback (timeout {initialization_timeout}s)... ")
    model_load_event.wait(timeout=initialization_timeout)
    asr_service.result_callback = original_callback # Restore original callback for transcription results

    if not asr_service.is_model_loaded: # Check the flag set by the worker
        print("Main thread: Model did not load (or signal not received). Exiting test.")
        asr_service.shutdown()
    else:
        print("Main thread: Model loaded. Simulating audio processing.")
        
        sample_rate = 16000
        num_chunks = 30 
        for i in range(num_chunks):
            dummy_chunk_int16 = np.random.randint(-1000, 1000, size=(1024, 1), dtype=np.int16)
            if i == num_chunks // 2:
                t = np.linspace(0, 1024/sample_rate, 1024, endpoint=False)
                sine_wave = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
                dummy_chunk_int16 = sine_wave.reshape(-1, 1)
            asr_service.process_audio_chunk(dummy_chunk_int16)

        audio_to_transcribe = asr_service.get_buffered_audio_and_clear()
        if audio_to_transcribe.size > 0:
            print(f"Main thread: Submitting audio of length {len(audio_to_transcribe)} for transcription.")
            asr_service.submit_transcription_request(audio_to_transcribe)
        else:
            print("Main thread: No audio buffered to transcribe.")

        print("Main thread: Simulating a second transcription request after 1s...")
        time.sleep(1)
        more_audio_int16 = np.random.randint(-500, 500, size=(8000,1), dtype=np.int16) # 0.5s
        asr_service.process_audio_chunk(more_audio_int16)
        more_audio_to_transcribe = asr_service.get_buffered_audio_and_clear()
        asr_service.submit_transcription_request(more_audio_to_transcribe)

        print("Main thread: Requests submitted. Waiting up to 15s for callbacks...")
        time.sleep(15) 

        print("Main thread: Shutting down ASRService.")
        asr_service.shutdown()

    print("ASRService test finished.") 