import asyncio
import fcntl
import logging
import os
import pty
import struct
import termios

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

terminal_router = APIRouter()


@terminal_router.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    """WebSocket-to-PTY bridge. Gives a full shell in the browser via xterm.js."""
    await websocket.accept()

    master_fd, slave_fd = pty.openpty()
    pid = os.fork()

    if pid == 0:
        # Child process — become the shell
        os.setsid()
        os.close(master_fd)

        # Set slave as controlling terminal
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

        # Redirect stdio to the PTY slave
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)

        shell = os.environ.get("SHELL", "/bin/bash")
        os.execvpe(shell, [shell, "--login"], os.environ)

    # Parent process — bridge WebSocket <-> PTY master
    os.close(slave_fd)

    # Make master_fd non-blocking
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    loop = asyncio.get_event_loop()

    async def pty_to_ws():
        """Read from PTY and send to WebSocket."""
        while True:
            try:
                data = await loop.run_in_executor(None, _blocking_read, master_fd)
                if data:
                    await websocket.send_text(data)
            except OSError:
                break
            except WebSocketDisconnect:
                break
            except Exception:
                break

    async def ws_to_pty():
        """Read from WebSocket and write to PTY."""
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                text = msg.get("text", "")
                if text.startswith("\x1b[resize:"):
                    # Handle resize: \x1b[resize:ROWS:COLS
                    try:
                        parts = text.split(":")
                        rows = int(parts[1])
                        cols = int(parts[2])
                        winsize = struct.pack("HHHH", rows, cols, 0, 0)
                        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                    except (ValueError, IndexError):
                        pass
                else:
                    os.write(master_fd, text.encode("utf-8", errors="replace"))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    try:
        read_task = asyncio.create_task(pty_to_ws())
        write_task = asyncio.create_task(ws_to_pty())
        await asyncio.wait(
            [read_task, write_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        read_task.cancel()
        write_task.cancel()
        os.close(master_fd)
        try:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        except OSError:
            pass
        logger.info("Terminal session closed")


def _blocking_read(fd: int) -> str:
    """Blocking read from PTY fd. Called in executor."""
    import select
    ready, _, _ = select.select([fd], [], [], 0.1)
    if ready:
        data = os.read(fd, 4096)
        return data.decode("utf-8", errors="replace")
    return ""
