import numpy as np
import threading
import sys

# Completely disable matplotlib on macOS to avoid GUI threading issues
if sys.platform == "darwin":
    # Create dummy matplotlib objects to avoid import errors
    class DummyMatplotlib:
        def use(self, backend): pass
        def ioff(self): pass
        def subplots(self): return None, None
        def close(self, fig): pass
    
    class DummyPlt:
        def ioff(self): pass
        def subplots(self): return None, None
        def close(self, fig): pass
    
    matplotlib = DummyMatplotlib()
    plt = DummyPlt()
else:
    import matplotlib
    # Use a non-interactive backend to avoid GUI threading issues
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

class WaveformVisualizer:
    def __init__(self, sample_rate=16000, buffer_seconds=5):
        self.sample_rate = sample_rate
        self.buffer_size = sample_rate * buffer_seconds
        self.buffer = np.zeros(self.buffer_size, dtype=np.int16)
        self.running = False
        self.lock = threading.Lock()
        
        # Completely disable visualization on macOS
        self.enable_visualization = not (sys.platform == "darwin")
        
        if self.enable_visualization:
            try:
                # Disable interactive plotting to avoid threading issues
                plt.ioff()
                self.fig, self.ax = plt.subplots()
                self.line, = self.ax.plot(self.buffer)
                self.ax.set_ylim(-32768, 32767)
                self.ax.set_xlim(0, self.buffer_size)
                self.ax.set_title("Recording waveform")
                self.ax.set_xlabel("Samples")
                self.ax.set_ylabel("Amplitude")
            except Exception as e:
                print(f"WAVEFORM_VISUALIZER: Could not create matplotlib figure: {e}")
                self.enable_visualization = False
        else:
            print("WAVEFORM_VISUALIZER: Visualization completely disabled on macOS to avoid threading issues")
            self.fig = None
            self.ax = None
            self.line = None

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
            
        if self.enable_visualization and self.fig:
            try:
                print("WAVEFORM_VISUALIZER: Visualization started (background mode)")
            except Exception as e:
                print(f"WAVEFORM_VISUALIZER: Error starting visualization: {e}")
        else:
            print("WAVEFORM_VISUALIZER: Start called but visualization is disabled")

    def stop(self):
        with self.lock:
            if not self.running:
                return
            self.running = False
            
        if self.enable_visualization and self.fig:
            try:
                plt.close(self.fig)
                print("WAVEFORM_VISUALIZER: Visualization stopped")
            except Exception as e:
                print(f"WAVEFORM_VISUALIZER: Error stopping visualization: {e}")
        else:
            print("WAVEFORM_VISUALIZER: Stop called but visualization is disabled")

    def add_chunk(self, chunk):
        with self.lock:
            if not self.running:
                return
                
        if not self.enable_visualization:
            return
            
        try:
            chunk = np.array(chunk).flatten()
            if chunk.dtype != np.int16:
                chunk = (chunk * 32767).astype(np.int16)
            n = len(chunk)
            
            with self.lock:
                if n >= self.buffer_size:
                    self.buffer[:] = chunk[-self.buffer_size:]
                else:
                    self.buffer = np.roll(self.buffer, -n)
                    self.buffer[-n:] = chunk
                    
        except Exception as e:
            print(f"WAVEFORM_VISUALIZER: Error processing chunk: {e}")
