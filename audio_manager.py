import sounddevice as sd
import numpy as np
import queue
import threading
import time
import logging

# Set up logging for audio manager
logger = logging.getLogger('AudioManager')

def log_print(*args, **kwargs):
    """Custom print function that logs to file"""
    message = ' '.join(str(arg) for arg in args)
    logger.info(message)
    import builtins
    builtins.print(*args, **kwargs)

print = log_print

class AudioManager:
    def __init__(self, sample_rate=16000, channels=1, dtype='int16', chunk_size=1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.chunk_size = chunk_size
        self._is_recording = False
        self._recording_thread = None
        self._recording_active_event = threading.Event()
        self._stream_ready_event = threading.Event()
        self._last_error = None
        self.audio_chunk_callback = None
        self.lock = threading.Lock() # Lock for synchronizing access to shared state like _is_recording

    def _recording_loop(self, caller_context="unknown_loop_start"):
        print(f"AUDIO_MANAGER ({caller_context}): Recording loop thread started.")
        stream = None
        try:
            # IMPORTANT: Refresh device cache to detect newly connected devices
            sd._terminate()
            sd._initialize()

            # Log default input device after refresh
            try:
                default_device = sd.query_devices(kind='input')
                print(f"AUDIO_MANAGER ({caller_context}): Default input device: {default_device['name']}")
            except Exception as e:
                print(f"AUDIO_MANAGER ({caller_context}): Could not query default device: {e}")

            print(f"AUDIO_MANAGER ({caller_context}): Attempting to open InputStream: SR={self.sample_rate}, Channels={self.channels}")
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                blocksize=self.chunk_size,
            ) as stream:
                self._stream_ready_event.set()
                print(f"AUDIO_MANAGER ({caller_context}): InputStream opened successfully. Entering read loop.")
                # _is_recording is set in start_recording under lock before thread starts
                while self._recording_active_event.is_set():
                    try:
                        chunk, overflowed = stream.read(self.chunk_size)
                        if not self._recording_active_event.is_set(): # Re-check after potentially blocking read
                            print(f"AUDIO_MANAGER ({caller_context}): Event cleared during/after stream.read, breaking loop.")
                            break 
                        if overflowed:
                            print(f"AUDIO_MANAGER ({caller_context}): Audio buffer overflowed!")
                        if self.audio_chunk_callback:
                            self.audio_chunk_callback(chunk.copy())
                    except sd.PortAudioError as pae:
                        self._last_error = pae
                        if pae.args[0] == 'Input overflowed':
                            print(f"AUDIO_MANAGER ({caller_context}): Warning - Input overflowed (PortAudioError)")
                        elif self._recording_active_event.is_set(): # Only log if we weren't already stopping
                             print(f"AUDIO_MANAGER ({caller_context}): PortAudioError in read loop: {pae}")
                             self._recording_active_event.clear() # Ensure stop on error
                             break
                        else:
                            print(f"AUDIO_MANAGER ({caller_context}): PortAudioError in read loop (event already cleared): {pae}")
                            break # Event was cleared, so just exit
                    except Exception as e:
                        self._last_error = e
                        if self._recording_active_event.is_set(): # Only log if we weren't already stopping
                            print(f"AUDIO_MANAGER ({caller_context}): Error reading from audio stream: {e}")
                        self._recording_active_event.clear() # Ensure stop on error
                        break
            print(f"AUDIO_MANAGER ({caller_context}): Exited read loop (event_set={self._recording_active_event.is_set()}).")
        except sd.PortAudioError as pae_outer:
            self._last_error = pae_outer
            self._stream_ready_event.set()
            self._recording_active_event.clear()
            print(f"AUDIO_MANAGER ({caller_context}): PortAudioError during stream setup/context: {pae_outer}")
        except Exception as e_outer:
            self._last_error = e_outer
            self._stream_ready_event.set()
            self._recording_active_event.clear()
            print(f"AUDIO_MANAGER ({caller_context}): General error in _recording_loop: {e_outer}")
        finally:
            print(f"AUDIO_MANAGER ({caller_context}): Recording loop 'finally' block executing.")
            self._stream_ready_event.set()
            if stream and not stream.closed:
                 print(f"AUDIO_MANAGER ({caller_context}): Stream was not closed by 'with' or error, attempting stop/close.")
                 try:
                     stream.stop()
                     stream.close()
                     print(f"AUDIO_MANAGER ({caller_context}): Stream explicitly stopped and closed in finally.")
                 except Exception as e_close:
                     print(f"AUDIO_MANAGER ({caller_context}): Error during final stream close attempt: {e_close}")
            
            with self.lock:
                self._is_recording = False # Ensure this is set False before thread truly exits
                print(f"AUDIO_MANAGER ({caller_context}): _is_recording SET to False in loop finally. Thread about to finish.")
            print(f"AUDIO_MANAGER ({caller_context}): Recording loop thread finished.")

    def start_recording(self, caller_context="unknown_start"):
        print(f"AUDIO_MANAGER ({caller_context}): start_recording called.")
        with self.lock:
            if self._is_recording:
                print(f"AUDIO_MANAGER ({caller_context}): Already recording (_is_recording=True). Returning False.")
                return False
            if self._recording_thread and self._recording_thread.is_alive():
                print(f"AUDIO_MANAGER ({caller_context}): Recording thread exists and is alive. Returning False.")
                return False

            print(f"AUDIO_MANAGER ({caller_context}): Preparing to start audio recording session...")
            self._recording_active_event.set() # Set event before starting thread
            self._is_recording = True # Set flag under lock
            self._last_error = None
            self._stream_ready_event.clear()
            print(f"AUDIO_MANAGER ({caller_context}): _is_recording SET to True, event SET.")
            
            self._recording_thread = threading.Thread(target=self._recording_loop, args=(caller_context,))
            self._recording_thread.daemon = True
            self._recording_thread.start()
            print(f"AUDIO_MANAGER ({caller_context}): Recording session initiated (thread started).")

        if not self._stream_ready_event.wait(timeout=2.0):
            print(f"AUDIO_MANAGER ({caller_context}): Timed out waiting for audio stream to initialize.")
            self._recording_active_event.clear()
            with self.lock:
                self._is_recording = False
                if self._recording_thread and not self._recording_thread.is_alive():
                    self._recording_thread = None
            return False

        if self._last_error is not None:
            print(f"AUDIO_MANAGER ({caller_context}): Audio stream failed to start: {self._last_error}")
            self._recording_active_event.clear()
            with self.lock:
                self._is_recording = False
                if self._recording_thread and not self._recording_thread.is_alive():
                    self._recording_thread = None
            return False

        return True

    def stop_recording(self, caller_context="unknown_stop"):
        print(f"AUDIO_MANAGER ({caller_context}): stop_recording called.")
        
        # Check if there's anything to stop first
        if not self._recording_active_event.is_set() and not self._is_recording:
            # It's possible the thread is alive but the event was cleared and _is_recording is False due to loop finalization
            # but the thread itself hasn't been joined from a previous stop_recording call.
            # This path indicates it's likely already stopped or in the process of stopping fully from another call.
            print(f"AUDIO_MANAGER ({caller_context}): stop_recording: Event not set and _is_recording is False. Likely already stopped or stopping.")
            # If thread object exists but isn't alive, clear it
            if self._recording_thread and not self._recording_thread.is_alive():
                with self.lock:
                    self._recording_thread = None
            return # Nothing to actively stop from this call's perspective

        print(f"AUDIO_MANAGER ({caller_context}): Clearing recording_active_event.")
        self._recording_active_event.clear()

        thread_to_join = None
        with self.lock:
            # _is_recording will be set to False by the recording_loop's finally block.
            # We primarily manage the event here and join the thread.
            if self._recording_thread:
                thread_to_join = self._recording_thread
        
        if thread_to_join and thread_to_join.is_alive():
            print(f"AUDIO_MANAGER ({caller_context}): Waiting for recording thread ({thread_to_join.name}) to finish...")
            thread_to_join.join(timeout=3.0) # Increased timeout slightly
            if thread_to_join.is_alive():
                print(f"AUDIO_MANAGER ({caller_context}): WARNING - Recording thread did not finish cleanly after stop signal and join timeout.")
            else:
                print(f"AUDIO_MANAGER ({caller_context}): Recording thread finished and joined.")
        else:
            print(f"AUDIO_MANAGER ({caller_context}): Recording thread was not alive or not initialized at stop, or already joined.")
        
        # Final state consolidation under lock
        with self.lock:
            self._is_recording = False # Explicitly ensure it's false
            self._recording_thread = None # Clear the thread object since it's stopped/joined
            print(f"AUDIO_MANAGER ({caller_context}): _is_recording robustly SET to False, thread object cleared. Session stopped.")

    def get_audio_chunk(self):
        try:
            print("AUDIO_MANAGER: get_audio_chunk called, but queue not actively used in new model.")
            return None 
        except queue.Empty:
            return None

    def set_chunk_callback(self, callback):
        self.audio_chunk_callback = callback

    def get_last_error(self):
        return self._last_error

    @staticmethod
    def list_microphones():
        print("Available microphones:")
        devices = sd.query_devices()
        input_devices = [dev for dev in devices if dev['max_input_channels'] > 0]
        if not input_devices:
            print("  No input devices found.")
            return
        for i, device in enumerate(input_devices):
            print(f"  {i}: {device['name']}")

if __name__ == '__main__':
    AudioManager.list_microphones()
    
    am = AudioManager()
    
    def my_chunk_processor(chunk):
        print(f"TEST_CALLBACK: Processing chunk of shape: {chunk.shape}, dtype: {chunk.dtype}")

    am.set_chunk_callback(my_chunk_processor)
    
    print("\n--- Test 1: Record for 3 seconds ---")
    input("Press Enter to start...")
    if am.start_recording():
        time.sleep(3)
        am.stop_recording()
        print("Test 1 finished.\n")
    else:
        print("Test 1: Could not start recording.\n")

    time.sleep(0.5)

    print("--- Test 2: Record again for 2 seconds (testing re-initialization) ---")
    input("Press Enter to start...")
    if am.start_recording():
        time.sleep(2)
        am.stop_recording()
        print("Test 2 finished.\n")
    else:
        print("Test 2: Could not start recording for the second time.\n")

    print("--- Test 3: Rapid start/stop (stress test) ---")
    input("Press Enter to start rapid start/stop test...")
    if am.start_recording():
        print("Rapid test: Started, stopping immediately.")
        am.stop_recording()
        print("Rapid test: Stopped.")
    else:
        print("Rapid test: Could not start recording.\n")
    time.sleep(0.5)
    if am.start_recording():
        print("Rapid test: Started again, stopping after 0.5s.")
        time.sleep(0.5)
        am.stop_recording()
        print("Rapid test: Stopped again.")
    else:
        print("Rapid test: Could not start second recording in rapid test.\n")

    print(" AudioManager tests complete.") 
