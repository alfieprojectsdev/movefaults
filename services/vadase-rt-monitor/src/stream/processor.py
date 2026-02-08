import structlog
from datetime import datetime
from typing import Optional
from src.parsers.nmea_parser import parse_lvm, parse_ldm, NMEAChecksumError
from src.utils.metrics import compute_horizontal_magnitude, convert_m_to_mm
from src.database.writer import DatabaseWriter
from src.sources.base import DataSource

logger = structlog.get_logger()

class IngestionProcessor:
    """
    Process NMEA data from a DataSource (File or TCP).
    Decoupled from the connection logic.
    """
    def __init__(
        self,
        source: DataSource,
        station_id: str,
        db_writer: DatabaseWriter,
        threshold_mm_s: float = 15.0,
        min_completeness: float = 0.5
    ):
        self.source = source
        self.station_id = station_id
        self.db_writer = db_writer
        self.threshold_mm_s = threshold_mm_s
        self.min_completeness = min_completeness
        
        self.logger = logger.bind(station=station_id, component="processor")
        
        # Event detection state
        self.event_active = False
        self.event_start_time: Optional[datetime] = None
        self.peak_velocity = 0.0
        self.peak_displacement = 0.0

    async def run(self):
        """
        Main processing loop. Iterates over source and processes sentences.
        """
        await self.source.connect()
        try:
            async for sentence in self.source:
                await self.process_sentence(sentence)
        finally:
            await self.source.close()

    async def process_sentence(self, sentence: str):
        """
        Parse and route NMEA sentence to appropriate handler
        """
        try:
            if sentence.startswith('$GNLVM') or sentence.startswith('$GPLVM'):
                await self.handle_velocity(sentence)
            
            elif sentence.startswith('$GNLDM') or sentence.startswith('$GPLDM'):
                await self.handle_displacement(sentence)
        
        except NMEAChecksumError:
            self.logger.warning("checksum_error", sentence=sentence[:50])
        except Exception as e:
            self.logger.error("processing_error", error=str(e), sentence=sentence[:50])

    async def handle_velocity(self, sentence: str):
        """Process LVM sentence and check for event detection"""
        data = parse_lvm(sentence)
        if not data:
            return
        
        # Compute horizontal magnitude
        vH = compute_horizontal_magnitude(data['vE'], data['vN'])
        data['vH_magnitude'] = vH
        
        # Write to database
        await self.db_writer.write_velocity(self.station_id, data)
        
        # Check threshold for event detection
        vH_mm_s = convert_m_to_mm(vH)
        await self.check_event_threshold(data['timestamp'], vH_mm_s)
    
    async def handle_displacement(self, sentence: str):
        """Process LDM sentence"""
        data = parse_ldm(sentence)
        if not data:
            return
        
        # Quality filtering
        if data['overall_completeness'] < self.min_completeness:
            # Low logging level to avoid spam
            # self.logger.debug("low_completeness_skipped")
            return
        
        # Compute horizontal magnitude
        dH = compute_horizontal_magnitude(data['dE'], data['dN'])
        data['dH_magnitude'] = dH
        
        # Track peak displacement during event
        if self.event_active:
            dH_mm = convert_m_to_mm(dH)
            if dH_mm > self.peak_displacement:
                self.peak_displacement = dH_mm
        
        # Write to database
        await self.db_writer.write_displacement(self.station_id, data)
    
    async def check_event_threshold(self, timestamp: datetime, vH_mm_s: float):
        """Detect event start/end based on velocity threshold"""
        if vH_mm_s > self.threshold_mm_s:
            if not self.event_active:
                # Event started
                self.event_active = True
                self.event_start_time = timestamp
                self.peak_velocity = vH_mm_s
                self.peak_displacement = 0.0
                
                self.logger.warning(
                    "event_detected",
                    timestamp=timestamp.isoformat(),
                    velocity_mm_s=vH_mm_s
                )
                await self.send_alert(timestamp, vH_mm_s)
            
            else:
                # Update peak velocity
                if vH_mm_s > self.peak_velocity:
                    self.peak_velocity = vH_mm_s
        
        else:
            if self.event_active:
                # Event ended - log detection
                duration = (timestamp - self.event_start_time).total_seconds()
                
                self.logger.info(
                    "event_ended",
                    start_time=self.event_start_time.isoformat(),
                    duration_sec=duration,
                    peak_velocity_mm_s=self.peak_velocity,
                    peak_displacement_mm=self.peak_displacement
                )
                
                # Write detection record
                await self.db_writer.write_event_detection(
                    station=self.station_id,
                    detection_time=self.event_start_time,
                    peak_velocity=self.peak_velocity,
                    peak_displacement=self.peak_displacement,
                    duration=duration
                )
                
                # Reset state
                self.event_active = False
                self.event_start_time = None
    
    async def send_alert(self, timestamp: datetime, velocity: float):
        """
        Send real-time alert via configured channels

        Args:
            timestamp: Detection timestamp
            velocity: Peak velocity triggering alert (mm/s)

        TODO: Implement alert mechanisms (email, Telegram, webhook)
        """
        self.logger.warning(
            "alert_triggered",
            timestamp=timestamp.isoformat(),
            velocity_mm_s=velocity
        )
