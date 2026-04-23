import asyncio
import structlog
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Dict, Any
from src.ports.outputs import OutputPort
from src.parsers.nmea_parser import parse_lvm, parse_ldm, NMEAChecksumError
from src.utils.metrics import compute_horizontal_magnitude, convert_m_to_mm

logger = structlog.get_logger()


class ReceiverMode(Enum):
    RECEIVER = auto()
    MANUAL   = auto()


STREAK_THRESHOLD   = 5
GOOD_THRESHOLD     = 30
SUSPECT_THRESHOLD  = 3


class IngestionCore:
    """
    Hexagonal Core: Consumes NMEA sentences from a queue and drives Output ports.
    Agnostic of where data comes from (File/TCP).
    Includes "Smart Integration" to handle bad receivers (Velocity-as-Displacement).
    """
    def __init__(
        self,
        station_id: str,
        output_port: OutputPort,
        threshold_mm_s: float = 15.0,
        min_completeness: float = 0.5,
        force_integration: bool = False,
        decay_factor: float = 1.0
    ):
        self.station_id = station_id
        self.output_port = output_port
        self.threshold_mm_s = threshold_mm_s
        self.min_completeness = min_completeness
        self.force_integration = force_integration
        self.decay_factor = decay_factor
        self.logger = logger.bind(station=station_id, component="core")

        # Event Detection State
        self.event_active = False
        self.event_start_time: Optional[datetime] = None
        self.peak_velocity = 0.0
        self.peak_displacement = 0.0

        # Smart Integration State
        self.mode = ReceiverMode.MANUAL if force_integration else ReceiverMode.RECEIVER
        self.disp_east = 0.0
        self.disp_north = 0.0
        self.disp_up = 0.0
        self.last_velocity_time: Optional[datetime] = None
        self.last_velocity_data: Optional[Dict[str, Any]] = None
        self.bad_streak     = 0
        self.good_streak    = 0
        self.suspect_streak = 0
        self._freeze_integration = False

    def _classify_signal(self, ve: float, vn: float, de: float, dn: float) -> str:
        is_identical = (abs(ve - de) < 1e-9) and (abs(vn - dn) < 1e-9)
        if is_identical:
            return "IDENTICAL"
        vH_mm_s = convert_m_to_mm(compute_horizontal_magnitude(ve, vn))
        return "HIGH_VEL_NEQ" if vH_mm_s >= self.threshold_mm_s else "LOW_VEL_NEQ"

    def _update_mode(self, signal: str) -> None:
        if self.mode == ReceiverMode.RECEIVER:
            if signal == "IDENTICAL":
                self.bad_streak += 1; self.good_streak = 0; self.suspect_streak = 0
                if self.bad_streak >= STREAK_THRESHOLD:
                    self.mode = ReceiverMode.MANUAL; self.bad_streak = 0
                    self._freeze_integration = False
                    self.logger.warning("mode_transition", to="MANUAL", reason="quiet_time")
            elif signal == "HIGH_VEL_NEQ":
                self.bad_streak = 0; self.good_streak = 0; self.suspect_streak = 0
                self._freeze_integration = False
            elif signal == "LOW_VEL_NEQ":
                self.bad_streak = 0; self.good_streak = 0; self.suspect_streak += 1
                if self.suspect_streak >= SUSPECT_THRESHOLD:
                    self.mode = ReceiverMode.MANUAL; self.suspect_streak = 0
                    self._freeze_integration = True
                    self.logger.warning("mode_transition", to="MANUAL", reason="scintillation")

        elif self.mode == ReceiverMode.MANUAL:
            if signal == "IDENTICAL":
                self.bad_streak += 1; self.good_streak = 0; self.suspect_streak = 0
                self._freeze_integration = False
            elif signal == "HIGH_VEL_NEQ":
                self.bad_streak = 0; self.good_streak += 1; self.suspect_streak = 0
                self._freeze_integration = False
                if self.good_streak >= GOOD_THRESHOLD:
                    self.mode = ReceiverMode.RECEIVER; self.good_streak = 0
                    self.logger.info("mode_transition", to="RECEIVER", reason="seismic_recovery")
            elif signal == "LOW_VEL_NEQ":
                self.bad_streak = 0; self.good_streak = 0; self.suspect_streak += 1
                self._freeze_integration = True

    async def consume(self, queue: asyncio.Queue, stop_event: asyncio.Event):
        """
        Main loop: Read from queue -> Process -> Write to Output
        """
        await self.output_port.connect()
        try:
            while not stop_event.is_set():
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

        # Store for displacement comparison/integration
        self.last_velocity_data = data

        # Standard Processing
        vH = compute_horizontal_magnitude(data['vE'], data['vN'])
        data['vH_magnitude'] = vH
        await self.output_port.write_velocity(self.station_id, data)

        # Check Event
        vH_mm_s = convert_m_to_mm(vH)
        await self.check_event_threshold(data['timestamp'], vH_mm_s)

        # Update Integration State
        current_time = data['timestamp']
        if self.last_velocity_time is not None:
            delta_t = (current_time - self.last_velocity_time).total_seconds()
            # Only integrate if gap is reasonable (e.g. < 5s) to avoid jumps after outages
            if 0 < delta_t < 5.0 and not self._freeze_integration:
                # Leaky Integrator (High-pass filter)
                # disp = (disp * decay) + (vel * dt)
                self.disp_east  = (self.disp_east  * self.decay_factor) + (data['vE'] * delta_t)
                self.disp_north = (self.disp_north * self.decay_factor) + (data['vN'] * delta_t)
                self.disp_up    = (self.disp_up    * self.decay_factor) + (data['vU'] * delta_t)
            # last_velocity_time still updates unconditionally (preserves delta_t continuity)

        self.last_velocity_time = current_time

    async def handle_displacement(self, sentence: str):
        data = parse_ldm(sentence)
        if not data: return
        if data['overall_completeness'] < self.min_completeness: return

        # Smart Integration Detection
        if self.last_velocity_data:
            ve, vn = self.last_velocity_data['vE'], self.last_velocity_data['vN']
            signal = self._classify_signal(ve, vn, data['dE'], data['dN'])
            self._update_mode(signal)

        if self.mode == ReceiverMode.MANUAL:
            data['dE'] = self.disp_east
            data['dN'] = self.disp_north
            data['dU'] = self.disp_up
            data['displacement_source'] = 'INTEGRATOR'
        elif self.suspect_streak > 0:
            data['displacement_source'] = 'RECEIVER_SUSPECT'
        else:
            data['displacement_source'] = 'RECEIVER'

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
