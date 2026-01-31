import matplotlib.pyplot as plt
from datetime import datetime
import asyncio
from typing import List, Deque
from collections import deque

import matplotlib.dates as mdates

class LivePlotter:
    """
    Real-time visualization of VADASE velocity stream (Displacement Component Debug).
    """
    def __init__(self, window_size: int = 600):
        self.window_size = window_size
        self.timestamps: Deque[datetime] = deque(maxlen=window_size)
        
        # Displacement Components
        self.de_hist: Deque[float] = deque(maxlen=window_size)
        self.dn_hist: Deque[float] = deque(maxlen=window_size)
        self.du_hist: Deque[float] = deque(maxlen=window_size)
        
        # 3 Rows: dE, dN, dU
        self.fig, (self.ax_e, self.ax_n, self.ax_u) = plt.subplots(3, 1, figsize=(10, 10), sharex=True)
        
        self.line_e, = self.ax_e.plot([], [], 'b-', label='Disp East (m)', linewidth=1)
        self.line_n, = self.ax_n.plot([], [], 'g-', label='Disp North (m)', linewidth=1)
        self.line_u, = self.ax_u.plot([], [], 'r-', label='Disp Up (m)', linewidth=1)
        
        # Setup Axes
        self.ax_e.set_ylabel('East (m)')
        self.ax_e.legend(loc='upper right')
        self.ax_e.grid(True)
        self.ax_e.axhline(0, color='black', linewidth=0.5)
        
        self.ax_n.set_ylabel('North (m)')
        self.ax_n.legend(loc='upper right')
        self.ax_n.grid(True)
        self.ax_n.axhline(0, color='black', linewidth=0.5)
        
        self.ax_u.set_ylabel('Up (m)')
        self.ax_u.set_xlabel('Time (UTC)')
        self.ax_u.legend(loc='upper right')
        self.ax_u.grid(True)
        self.ax_u.axhline(0, color='black', linewidth=0.5)
        
        # Date Formatting
        self.ax_u.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        plt.setp(self.ax_u.get_xticklabels(), rotation=45, ha='right')
        
        plt.ion()
        plt.show()

    async def connect(self):
        pass

    async def close(self):
        plt.ioff()
        plt.show()

    async def write_velocity(self, station_id, data):
        # We process mainly on displacement updates now, but keep timestamps synced if needed
        pass

    async def write_displacement(self, station_id, data):
        self.timestamps.append(data['timestamp'])
        self.de_hist.append(data.get('dE', 0.0))
        self.dn_hist.append(data.get('dN', 0.0))
        self.du_hist.append(data.get('dU', 0.0))
        self._update_plot(station_id)

    async def write_event_detection(self, station, detection_time, peak_velocity, peak_displacement, duration):
        for ax in [self.ax_e, self.ax_n, self.ax_u]:
            ax.axvline(x=detection_time, color='r', linestyle='--', alpha=0.5)

    def _update_plot(self, station_id):
        if not self.timestamps:
            return
            
        t = list(self.timestamps)
        
        self.line_e.set_data(t, list(self.de_hist))
        self.line_n.set_data(t, list(self.dn_hist))
        self.line_u.set_data(t, list(self.du_hist))
        
        for ax in [self.ax_e, self.ax_n, self.ax_u]:
            ax.relim()
            ax.autoscale_view()
        
        self.fig.suptitle(f"Station: {station_id} - Displacement Components (Decay Verified)")
        plt.pause(0.001)
