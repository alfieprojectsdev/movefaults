import asyncio
import typer
import structlog
from pathlib import Path

app = typer.Typer()
logger = structlog.get_logger()

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, file_path: Path, rate: float):
    addr = writer.get_extra_info('peername')
    logger.info("client_connected", address=addr)

    try:
        # 1. NTRIP Handshake
        # Read request header (simplified: just read first chunk)
        request = await reader.read(4096)
        request_str = request.decode('ascii', errors='ignore')
        
        if "GET" in request_str:
            logger.info("received_ntrip_request", request=request_str.split('\r\n')[0])
            # Respond with NTRIP OK
            response = b"ICY 200 OK\r\nContent-Type: text/plain\r\n\r\n"
            writer.write(response)
            await writer.drain()
            logger.info("sent_handshake_response")
        else:
            logger.warning("unknown_request", request=request_str[:50])
            # Even if unknown, we might stream anyway if it's a raw socket test, 
            # but usually we expect NTRIP. Let's proceed to stream.

        # 2. Streaming Loop
        while True:
            logger.info("starting_file_stream", file=str(file_path))
            if not file_path.exists():
                logger.error("file_not_found", path=str(file_path))
                break
                
            with open(file_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    try:
                        writer.write(line.encode())
                        await writer.drain()
                        
                        # Simulate Rate
                        await asyncio.sleep(1.0 / rate)
                    except (ConnectionResetError, BrokenPipeError):
                        logger.warning("client_disconnected", address=addr)
                        return
                    except Exception as e:
                        logger.error("stream_error", error=str(e))
                        return
            
            # Loop
            logger.info("end_of_file_looping")
            await asyncio.sleep(0.5)

    except Exception as e:
        logger.error("handler_error", error=str(e))
    finally:
        writer.close()
        await writer.wait_closed()
        logger.info("connection_closed", address=addr)

async def start_server(host: str, port: int, file: Path, rate: float):
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, file, rate), 
        host, port
    )
    
    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    logger.info("server_started", listening_on=addrs, source_file=str(file))

    async with server:
        await server.serve_forever()

@app.command()
def main(
    file: Path = typer.Option(..., "--file", "-f", help="Path to NMEA/RTL file to stream"),
    port: int = typer.Option(2101, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host interface to bind"),
    rate: float = typer.Option(1.0, "--rate", "-r", help="Streaming rate in Hz (lines per second)")
):
    """
    Mock NTRIP Caster.
    Listens for TCP connections, accepts NTRIP GET requests, and streams content from a file indefinitely.
    """
    if not file.exists():
        logger.error(f"Source file not found: {file}")
        raise typer.Exit(code=1)
        
    try:
        asyncio.run(start_server(host, port, file, rate))
    except KeyboardInterrupt:
        logger.info("server_stopped_by_user")

if __name__ == "__main__":
    app()
