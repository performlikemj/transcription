import numpy as np
import matplotlib.pyplot as plt

class WaveformVisualizer:
    def __init__(self, sample_rate=16000, buffer_seconds=5):
        self.sample_rate = sample_rate
        self.buffer_size = sample_rate * buffer_seconds
        self.buffer = np.zeros(self.buffer_size, dtype=np.int16)
        self.running = False
        self.fig, self.ax = plt.subplots()
        self.line, = self.ax.plot(self.buffer)
        self.ax.set_ylim(-32768, 32767)
        self.ax.set_xlim(0, self.buffer_size)
        self.ax.set_title("Recording waveform")
        self.ax.set_xlabel("Samples")
        self.ax.set_ylabel("Amplitude")
        plt.ion()

    def start(self):
        if self.running:
            return
        self.running = True
        self.fig.show()
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

    def stop(self):
        if not self.running:
            return
        self.running = False
        plt.close(self.fig)

    def add_chunk(self, chunk):
        if not self.running:
            return
        chunk = np.array(chunk).flatten()
        if chunk.dtype != np.int16:
            chunk = (chunk * 32767).astype(np.int16)
        n = len(chunk)
        if n >= self.buffer_size:
            self.buffer[:] = chunk[-self.buffer_size:]
        else:
            self.buffer = np.roll(self.buffer, -n)
            self.buffer[-n:] = chunk
        self.line.set_ydata(self.buffer)
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()
