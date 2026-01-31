import matplotlib.pyplot as plt
from datetime import datetime
import asyncio
from typing import List, Deque
from collections import deque

class LivePlotter:
    """
    Real-time visualization of VADASE velocity stream.
    Acts as a 'writer' interface to be pluggable into IngestionProcessor.
    """
    def __init__(self, window_size: int = 600):
        self.window_size = window_size
        self.timestamps: Deque[datetime] = deque(maxlen=window_size)
        self.velocities: Deque[float] = deque(maxlen=window_size)
        self.displacements: Deque[float] = deque(maxlen=window_size)
        
        self.fig, (self.ax_vel, self.ax_disp) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
        self.line_vel, = self.ax_vel.plot([], [], 'b-', label='Horiz. Velocity (m/s)')
        self.line_disp, = self.ax_disp.plot([], [], 'g-', label='Horiz. Displacement (m)')
        
        self.ax_vel.set_ylabel('Velocity (m/s)')
        self.ax_vel.legend(loc='upper right')
        self.ax_vel.grid(True)
        
        self.ax_disp.set_ylabel('Displacement (m)')
        self.ax_disp.set_xlabel('Time (UTC)')
        self.ax_disp.legend(loc='upper right')
        self.ax_disp.grid(True)
        
        plt.ion()  # Interactive mode
        plt.show()

    async def connect(self):
        pass

    async def close(self):
        plt.ioff()
        plt.show()  # Keep window open at end

    async def write_velocity(self, station_id, data):
        """
        Update the velocity plot.
        Note: This blocks the async loop for a tiny fraction to redraw.
        """
        # We only plot velocity events here, storing them aligned to timestamp
        self.timestamps.append(data['timestamp'])
        self.velocities.append(data.get('vH_magnitude', 0.0))
        
        # Ensure lists are synced (simple simplistic approach)
        if len(self.displacements) < len(self.timestamps):
             self.displacements.append(0.0) # Pad if displacement missing

        self._update_plot(station_id)

    async def write_displacement(self, station_id, data):
        """
        Update displacement data. 
        Note: We assume velocity comes first or at similar rate.
        """
        # If we just added a timestamp from velocity, update the last displacement
        # Or if displacement comes alone? VADASE usually pairs them.
        # For simplicity, let's just update the last element if timestamps match, 
        # or append new if needed.
        
        ts = data['timestamp']
        dH = data.get('dH_magnitude', 0.0)
        
        if self.timestamps and self.timestamps[-1] == ts:
             # Update last placeholder
             if self.displacements:
                self.displacements[-1] = dH
        else:
            # New timestamp (displacement came first or standalone)
            self.timestamps.append(ts)
            self.displacements.append(dH)
            if len(self.velocities) < len(self.timestamps):
                self.velocities.append(0.0)

        # We update plot in write_velocity usually to save redraws, but okay to do here too
        # self._update_plot(station_id)
    
    async def write_event_detection(self, station, detection_time, peak_velocity, peak_displacement, duration):
        # Annotate plot
        self.ax_vel.axvline(x=detection_time, color='r', linestyle='--', alpha=0.5)
        self.ax_disp.axvline(x=detection_time, color='r', linestyle='--', alpha=0.5)
        self.ax_vel.text(detection_time, peak_velocity, "EVENT", color='red', rotation=90)

    def _update_plot(self, station_id):
        # Convert deque to list for plotting
        t = list(self.timestamps)
        v = list(self.velocities)
        d = list(self.displacements)
        
        self.line_vel.set_data(t, v)
        self.line_disp.set_data(t, d)
        
        self.ax_vel.relim()
        self.ax_vel.autoscale_view()
        self.ax_disp.relim()
        self.ax_disp.autoscale_view()
        
        self.fig.suptitle(f"Station: {station_id} - Live Monitor")
        
        # Pause to allow GUI event loop to process
        # 0.001 is minimal but allows window updates
        plt.pause(0.001)
