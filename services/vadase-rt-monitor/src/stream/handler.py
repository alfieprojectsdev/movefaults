"""
Async stream handler for VADASE NMEA data ingestion
Manages TCP connections to multiple CORS stations
"""

import asyncio
from datetime import datetime
from typing import Optional
import structlog

from src.parsers.nmea_parser import parse_lvm, parse_ldm, NMEAChecksumError
from src.utils.metrics import compute_horizontal_magnitude, convert_m_to_mm
from src.database.writer import DatabaseWriter

logger = structlog.get_logger()


class VADASEStreamHandler:
    """
    Handles TCP stream from a single VADASE-enabled CORS station
    
    Features:
    - Automatic reconnection on connection loss
    - NMEA sentence buffering and parsing
    - Quality filtering based on data completeness
    - Event detection with configurable thresholds
    """
    
    def __init__(
        self,
        station_id: str,
        host: str,
        port: int,
        db_writer: DatabaseWriter,
        threshold_mm_s: float = 15.0,
        min_completeness: float = 0.5
    ):
        """
        Initialize stream handler
        
        Args:
            station_id: Unique station identifier (e.g., 'PBIS')
            host: Receiver IP address
            port: TCP port for NMEA stream
            db_writer: Database writer instance
            threshold_mm_s: Velocity threshold for event detection (mm/s)
            min_completeness: Minimum data completeness ratio to accept (0-1)
        """
        self.station_id = station_id
        self.host = host
        self.port = port
        self.db_writer = db_writer
        self.threshold_mm_s = threshold_mm_s
        self.min_completeness = min_completeness
        
        # Event detection state
        self.event_active = False
        self.event_start_time: Optional[datetime] = None
        self.peak_velocity = 0.0
        self.peak_displacement = 0.0
        
        # Buffer for NMEA sentences
        self.buffer = ""
        
        self.logger = logger.bind(station=station_id)
    
    async def connect(self):
        """
        Maintain persistent connection with automatic reconnection
        Main entry point for running the stream handler
        """
        while True:
            try:
                self.logger.info("connecting", host=self.host, port=self.port)
                
                reader, writer = await asyncio.open_connection(self.host, self.port)
                self.logger.info("connected")
                
                while True:
                    # Read with timeout to detect stale connections
                    data = await asyncio.wait_for(reader.read(4096), timeout=30.0)
                    
                    if not data:
                        self.logger.warning("connection_closed_by_receiver")
                        break
                    
                    # Accumulate data in buffer
                    self.buffer += data.decode('ascii', errors='ignore')
                    
                    # Process complete sentences
                    while '\n' in self.buffer:
                        sentence, self.buffer = self.buffer.split('\n', 1)
                        sentence = sentence.strip()
                        
                        if sentence:
                            await self.process_sentence(sentence)
                
                writer.close()
                await writer.wait_closed()
                
            except asyncio.TimeoutError:
                self.logger.warning("timeout_no_data", timeout_sec=30)
            except Exception as e:
                self.logger.error("connection_error", error=str(e))
            
            # Wait before reconnecting
            self.logger.info("reconnecting_in", seconds=5)
            await asyncio.sleep(5)
    
    async def process_sentence(self, sentence: str):
        """
        Parse and route NMEA sentence to appropriate handler
        
        Args:
            sentence: Complete NMEA sentence (no newline)
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
        
        # Quality filtering: skip if data completeness is too low
        if data['overall_completeness'] < self.min_completeness:
            self.logger.debug(
                "low_completeness_skipped",
                completeness=data['overall_completeness']
            )
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
        """
        Detect event start/end based on velocity threshold
        
        Args:
            timestamp: Observation timestamp
            vH_mm_s: Horizontal velocity magnitude (mm/s)
        """
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