"""MLLP: the framing legacy systems use to send HL7 v2 over TCP.

Each message is wrapped as:  <VT> message <FS><CR>
  VT = 0x0B (start block), FS = 0x1C (end block), CR = 0x0D

The receiver replies with an ACK (MSA|AA = accepted, AE = error).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

START, END, CR = b"\x0b", b"\x1c", b"\x0d"
log = logging.getLogger("flowdeck.mllp")


def frame(message: str) -> bytes:
    return START + message.encode("utf-8") + END + CR


def unframe(buffer: bytes) -> tuple[list[str], bytes]:
    """Pull complete messages out of a byte buffer; return (messages, leftover)."""
    messages: list[str] = []
    while True:
        start = buffer.find(START)
        end = buffer.find(END + CR, start + 1)
        if start == -1 or end == -1:
            return messages, buffer
        messages.append(buffer[start + 1 : end].decode("utf-8"))
        buffer = buffer[end + 2 :]


def build_ack(raw: str, code: str = "AA", text: str = "") -> str:
    """Build a minimal ACK. code: AA accept, AE error, AR reject."""
    msh = raw.split("\r")[0].split("|")
    control_id = msh[9] if len(msh) > 9 else ""
    sending_app = msh[2] if len(msh) > 2 else ""
    sending_fac = msh[3] if len(msh) > 3 else ""
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    return "\r".join(
        [
            f"MSH|^~\\&|FLOWDECK|FLOWDECK|{sending_app}|{sending_fac}|{now}||ACK|ACK{control_id}|P|2.5.1",
            f"MSA|{code}|{control_id}|{text}",
        ]
    )


Handler = Callable[[str], Awaitable[None]]


async def serve(handler: Handler, host: str = "0.0.0.0", port: int = 2575) -> asyncio.Server:
    """Start an MLLP listener. ``handler`` receives each raw message."""

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        buffer = b""
        try:
            while chunk := await reader.read(65536):
                buffer += chunk
                messages, buffer = unframe(buffer)
                for msg in messages:
                    try:
                        await handler(msg)
                        ack = build_ack(msg, "AA")
                    except Exception as exc:  # report, never crash the listener
                        log.warning("Rejected message: %s", exc)
                        ack = build_ack(msg, "AE", str(exc)[:80])
                    writer.write(frame(ack))
                    await writer.drain()
        finally:
            writer.close()

    server = await asyncio.start_server(on_client, host, port)
    log.info("MLLP listener on %s:%s", host, port)
    return server


async def send(messages: list[str], host: str = "127.0.0.1", port: int = 2575) -> list[str]:
    """Client helper used by the simulator and tests. Returns the ACKs."""
    reader, writer = await asyncio.open_connection(host, port)
    acks: list[str] = []
    buffer = b""
    try:
        for msg in messages:
            writer.write(frame(msg))
            await writer.drain()
            while True:
                buffer += await reader.read(65536)
                got, buffer = unframe(buffer)
                if got:
                    acks.extend(got)
                    break
    finally:
        writer.close()
        await writer.wait_closed()
    return acks
