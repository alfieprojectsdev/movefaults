from datetime import datetime
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseWriter:
    def __init__(self):
        self.dsn = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        self.pool = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.dsn, min_size=5, max_size=20)
    
    async def write_velocity(self, data):
        """Insert velocity measurement"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO vadase_velocity (time, station, vN, vE, vU, quality)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (time, station) DO NOTHING
            ''', data['timestamp'], data['station'], 
                data['vN'], data['vE'], data['vU'], data['quality'])
    
    async def write_displacement(self, data):
        """Insert displacement measurement"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO vadase_displacement (time, station, dN, dE, dU, quality)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (time, station) DO NOTHING
            ''', data['timestamp'], data['station'],
                data['dN'], data['dE'], data['dU'], data['quality'])
