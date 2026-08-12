import asyncio
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daemon.server import DaemonServer
from tests.test_daemon import StubKernel


# Helper protocol to act as a client over the Named Pipe
class ClientProtocol(asyncio.Protocol):
    def __init__(self, on_connect, on_message) -> None:
        self.transport = None
        self.buffer = b""
        self.on_connect = on_connect
        self.on_message = on_message

    def connection_made(self, transport) -> None:
        self.transport = transport
        self.on_connect.set_result(self)

    def data_received(self, data: bytes) -> None:
        self.buffer += data
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if line:
                import json
                self.on_message(json.loads(line.decode()))

    def connection_lost(self, exc) -> None:
        pass


@pytest.mark.asyncio
async def test_named_pipe_ipc_lifecycle():
    loop = asyncio.get_running_loop()

    # Create temporary directories so we don't pollute the user space
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        registry_dir = tmp_path / "registry"
        state_dir = tmp_path / "state"
        project_dir = tmp_path / "project"
        registry_dir.mkdir()
        state_dir.mkdir()
        project_dir.mkdir()

        # Instantiate Daemon Server with StubKernel
        server = DaemonServer(
            kernel_factory=lambda **kw: StubKernel(events=2, delay=0.01),
            project_dir=str(project_dir),
            registry_dir=registry_dir,
            state_dir=state_dir,
        )

        await server.start()

        # Formulate pipe name
        pipe_name = rf"\\.\pipe\jarvis-{server.project_id}"

        # Connect to the pipe
        conn_fut = loop.create_future()
        received_messages = []

        def handle_message(msg):
            received_messages.append(msg)

        protocol_factory = lambda: ClientProtocol(conn_fut, handle_message)

        # Connect to pipe on Windows
        transport, protocol = await loop.create_pipe_connection(protocol_factory, pipe_name)
        await conn_fut

        # 1. Send authentication message
        auth_msg = {
            "version": 1,
            "id": "1",
            "type": "auth",
            "timestamp": time.time(),
            "payload": {"token": server.token}
        }
        transport.write(json_encode_msg(auth_msg))

        # Wait for auth response
        await asyncio.sleep(0.1)
        assert len(received_messages) == 1
        assert received_messages[0]["type"] == "ok"

        # 2. Send ping message
        ping_msg = {
            "version": 1,
            "id": "2",
            "type": "ping",
            "timestamp": time.time(),
            "payload": {}
        }
        transport.write(json_encode_msg(ping_msg))

        # Wait for pong response
        await asyncio.sleep(0.1)
        assert len(received_messages) == 2
        assert received_messages[1]["type"] == "pong"
        assert received_messages[1]["payload"]["project_id"] == server.project_id

        # Clean close client transport
        transport.close()

        # Stop the server daemon
        await server.shutdown()


def json_encode_msg(msg: dict) -> bytes:
    import json
    return (json.dumps(msg) + "\n").encode("utf-8")
