#!/usr/bin/env python3
"""
OrbitVPN Manager Web Dashboard Daemon

Run the web dashboard server.
"""
import sys
from pathlib import Path
import click
import uvicorn

sys.path.insert(0, str(Path(__file__).parent))

from manager.web.app import create_app
from manager.config.manager_config import load_config


@click.command()
@click.option('--host', default=None, help='Host to bind (default: from config)')
@click.option('--port', default=None, type=int, help='Port to bind (default: from config)')
@click.option('--reload', is_flag=True, help='Enable auto-reload for development')
def main(host: str, port: int, reload: bool):
    """Start the OrbitVPN Manager web dashboard."""

    config = load_config()

    host = host or config.web_dashboard.host
    port = port or config.web_dashboard.port

    click.echo(f"""
╔════════════════════════════════════════╗
║   OrbitVPN Manager Web Dashboard      ║
╚════════════════════════════════════════╝

Starting server on http://{host}:{port}

Press Ctrl+C to stop
    """)

    app = create_app()

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()

