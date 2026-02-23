"""
UE5 Command Listener - Run ONCE via Tools > Execute Python Script.
After this, Claude can push commands directly to UE5.
Stays active for the entire editor session.
"""
import unreal
import socket
import json
import threading
import queue
import traceback

PORT = 9876
_cmd_queue = queue.Queue()

def _listener_thread():
    """Background thread: accepts TCP connections, queues commands."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(('127.0.0.1', PORT))
    except OSError:
        unreal.log_warning(f"Port {PORT} already in use - listener may already be running")
        return
    server.listen(5)
    server.settimeout(2.0)

    while True:
        try:
            conn, addr = server.accept()
            data = b''
            conn.settimeout(120.0)
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
                if data.endswith(b'\n__END__\n'):
                    break
            command = data[:-9].decode('utf-8')
            event = threading.Event()
            result_holder = [None]
            _cmd_queue.put((command, conn, event, result_holder))
            event.wait(timeout=120)
        except socket.timeout:
            continue
        except Exception as e:
            pass

def _tick(delta_time):
    """Main thread tick: executes queued commands safely on game thread."""
    while not _cmd_queue.empty():
        try:
            command, conn, event, result_holder = _cmd_queue.get_nowait()
        except queue.Empty:
            break

        result = {"success": True, "output": "", "error": ""}

        # Capture output by monkey-patching unreal.log temporarily
        log_lines = []
        original_log = unreal.log
        original_warn = unreal.log_warning
        original_err = unreal.log_error

        def capture_log(msg):
            log_lines.append(str(msg))
            original_log(msg)
        def capture_warn(msg):
            log_lines.append(f"WARNING: {msg}")
            original_warn(msg)
        def capture_err(msg):
            log_lines.append(f"ERROR: {msg}")
            original_err(msg)

        unreal.log = capture_log
        unreal.log_warning = capture_warn
        unreal.log_error = capture_err

        try:
            exec_globals = {
                "unreal": unreal,
                "__builtins__": __builtins__,
                "__name__": "__remote__",
            }
            exec(command, exec_globals)
            result["success"] = True
        except Exception as e:
            result["success"] = False
            result["error"] = traceback.format_exc()
            log_lines.append(f"EXCEPTION: {traceback.format_exc()}")
        finally:
            unreal.log = original_log
            unreal.log_warning = original_warn
            unreal.log_error = original_err

        result["output"] = "\n".join(log_lines)

        try:
            response = json.dumps(result).encode('utf-8')
            conn.sendall(response)
            conn.close()
        except:
            pass

        event.set()

# Start listener thread
_thread = threading.Thread(target=_listener_thread, daemon=True)
_thread.start()

# Register tick callback for main-thread execution
_handle = unreal.register_slate_post_tick_callback(_tick)

unreal.log("")
unreal.log("=" * 50)
unreal.log("  COMMAND LISTENER ACTIVE (port 9876)")
unreal.log("  Claude can now push commands directly!")
unreal.log("=" * 50)
