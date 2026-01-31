import asyncio
import structlog
from datetime import datetime
from typing import Optional
from src.ports.outputs import OutputPort
from src.parsers.nmea_parser import parse_lvm, parse_ldm, NMEAChecksumError
from src.utils.metrics import compute_horizontal_magnitude, convert_m_to_mm

logger = structlog.get_logger()

class IngestionCore:
    """
    Hexagonal Core: Consumes NMEA sentences from a queue and drives Output ports.
    Agnostic of where data comes from (File/TCP).
    """
    def __init__(
        self,
        station_id: str,
        output_port: OutputPort,
        threshold_mm_s: float = 15.0,
        min_completeness: float = 0.5
    ):
        self.station_id = station_id
        self.output_port = output_port
        self.threshold_mm_s = threshold_mm_s
        self.min_completeness = min_completeness
        self.logger = logger.bind(station=station_id, component="core")
        
        # State
        self.event_active = False
        self.event_start_time: Optional[datetime] = None
        self.peak_velocity = 0.0
        self.peak_displacement = 0.0

    async def consume(self, queue: asyncio.Queue, stop_event: asyncio.Event):
        """
        Main loop: Read from queue -> Process -> Write to Output
        """
        await self.output_port.connect()
        try:
            while not stop_event.is_set():
                # Get item with timeout to check stop_event occasionally if queue is empty
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                if line is None: # Sentinel
                    break
                
                await self.process_sentence(line)
                queue.task_done()
        finally:
            await self.output_port.close()

    async def process_sentence(self, sentence: str):
        try:
            if sentence.startswith('$GNLVM') or sentence.startswith('$GPLVM'):
                await self.handle_velocity(sentence)
            elif sentence.startswith('$GNLDM') or sentence.startswith('$GPLDM'):
                await self.handle_displacement(sentence)
        except NMEAChecksumError:
            self.logger.warning("checksum_error")
        except Exception as e:
            self.logger.error("processing_error", error=str(e))

    async def handle_velocity(self, sentence: str):
        data = parse_lvm(sentence)
        if not data: return
        
        vH = compute_horizontal_magnitude(data['vE'], data['vN'])
        data['vH_magnitude'] = vH
        
        await self.output_port.write_velocity(self.station_id, data)
        
        vH_mm_s = convert_m_to_mm(vH)
        await self.check_event_threshold(data['timestamp'], vH_mm_s)

    async def handle_displacement(self, sentence: str):
        data = parse_ldm(sentence)
        if not data: return
        
        if data['overall_completeness'] < self.min_completeness: return
        
        dH = compute_horizontal_magnitude(data['dE'], data['dN'])
        data['dH_magnitude'] = dH
        
        if self.event_active:
            dH_mm = convert_m_to_mm(dH)
            if dH_mm > self.peak_displacement:
                self.peak_displacement = dH_mm
        
        await self.output_port.write_displacement(self.station_id, data)

    async def check_event_threshold(self, timestamp: datetime, vH_mm_s: float):
        if vH_mm_s > self.threshold_mm_s:
            if not self.event_active:
                self.event_active = True
                self.event_start_time = timestamp
                self.peak_velocity = vH_mm_s
                self.peak_displacement = 0.0
                self.logger.warning("event_detected", velocity=vH_mm_s)
            else:
                if vH_mm_s > self.peak_velocity:
                    self.peak_velocity = vH_mm_s
        else:
            if self.event_active:
                duration = (timestamp - self.event_start_time).total_seconds()
                self.logger.info("event_ended", duration=duration)
                await self.output_port.write_event_detection(
                    self.station_id, self.event_start_time, 
                    self.peak_velocity, self.peak_displacement, duration
                )
                self.event_active = False
