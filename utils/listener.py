import keyboard
import time
import logging
from threading          import Thread, Lock, Event
from concurrent.futures import ThreadPoolExecutor
from typing             import Set, Callable

# Type aliases for clarity
ScanCode      = int
BitIndex      = int
HashKey       = str
CallbackFunc  = Callable[[], None]


# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(levelname)s - %(message)s",
#     handlers=[
#         logging.StreamHandler(),
#         logging.FileHandler("hotkey_app.log")
#     ]
# )


class HotkeyError(Exception):
    """Raised when hotkey registration or removal fails."""
    pass


class Listener:
    """
    Listens for keyboard hotkey combinations and executes callbacks in a thread-safe manner.

    Features:
        - Background thread for non-blocking key event monitoring.
        - Thread-safe hotkey registration and removal.
        - Non-blocking callback execution via a thread pool.
        - Graceful shutdown and resource cleanup.
        - Context manager support for RAII-style usage.
    """

    def __init__(self, max_callback_workers: int = 1, debounce_ms: int = 500):
        """
        Initialize the hotkey listener.

        Args:
            max_callback_workers: Maximum number of threads for callback execution.
            debounce_ms: Minimum time (ms) between consecutive callback triggers.

        Raises:
            ValueError: If max_callback_workers or debounce_ms is invalid.
        """
        if max_callback_workers < 1:
            raise ValueError("max_callback_workers must be at least 1")
        if debounce_ms < 0:
            raise ValueError("debounce_ms must be non-negative")

        self._pressed_keys          = set()
        self._hotkey_map            = {}
        self._key_to_bit_index      = {}
        self._available_bit_indices = set(range(64))
        self._lock                  = Lock()
        self._stop_event            = Event()
        self._last_callback_time    = 0
        self._debounce_ms           = debounce_ms

        self._callback_executor     = ThreadPoolExecutor(
            max_workers             = max_callback_workers,
            thread_name_prefix      = 'HotkeyCallback'
        )
        self._listener_thread       = Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()
        logging.debug("Hotkey listener thread started")

    def __enter__(self):
        """Enable context manager usage."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure cleanup on context exit."""
        self.stop()

    def _get_scan_code(self, key_name: str) -> ScanCode:
        """
        Convert a key name to its primary scan code.

        Args:
            key_name: The key name (e.g., 'ctrl', 'left ctrl').

        Returns:
            The primary scan code.

        Raises:
            HotkeyError: If the key name is invalid or has no scan code.
        """
        try:
            scan_codes = keyboard.key_to_scan_codes(key_name)
            if len(scan_codes) > 1:
                logging.debug(f"Multiple scan codes for '{key_name}': {scan_codes}, using {scan_codes[0]}")
            return scan_codes[0]
        except ValueError as e:
            raise HotkeyError(f"Invalid key name '{key_name}': {e}")
        except Exception as e:
            raise HotkeyError(f"Error resolving scan code for '{key_name}': {e}")

    def _calculate_hash(self, scan_codes: Set[ScanCode]) -> HashKey:
        """
        Calculate a hash for a set of scan codes.

        Args:
            scan_codes: Set of scan codes to hash.

        Returns:
            A hexadecimal string representing the hash.
        """
        current_hash = 0
        for code in scan_codes:
            if code in self._key_to_bit_index:
                current_hash |= (1 << self._key_to_bit_index[code])
        return hex(current_hash)

    def _listen_loop(self):
        """
        Monitor keyboard events and trigger callbacks for hotkey matches.
        Uses ThreadPoolExecutor to run callbacks non-blocking.
        """
        logging.debug("Listener loop started")

        while not self._stop_event.is_set():
            try:
                event = keyboard.read_event(suppress=False)
                if not event.name or event.event_type not in ('down', 'up'):
                    continue
                scan_code = self._get_scan_code(event.name.lower())
                with self._lock:
                    is_relevant_key = scan_code in self._key_to_bit_index
                    if event.event_type == 'down' and is_relevant_key and scan_code not in self._pressed_keys:
                        self._pressed_keys.add(scan_code)
                        logging.debug(f"Key down: {event.name}, pressed_keys={self._pressed_keys}")
                        current_hash  = self._calculate_hash(self._pressed_keys)
                        current_time  = time.time() * 1000
                        if current_hash in self._hotkey_map and (current_time - self._last_callback_time) >= self._debounce_ms:
                            callback_to_run = self._hotkey_map[current_hash]
                            logging.info(f"Hotkey triggered: hash={current_hash}")
                            try:
                                self._callback_executor.submit(callback_to_run)
                                logging.debug(f"Submitted callback for hash={current_hash}")
                                self._last_callback_time = current_time
                            except RuntimeError:
                                logging.warning(f"Callback queue full, skipping hotkey: hash={current_hash}")
                    elif event.event_type == 'up' and scan_code in self._pressed_keys:
                        self._pressed_keys.discard(scan_code)
                        logging.debug(f"Key up: {event.name}, pressed_keys={self._pressed_keys}")
            except HotkeyError:
                continue
            except Exception as e:
                if not self._stop_event.is_set():
                    logging.error(f"Listener loop error: {e}")
                    time.sleep(0.05)

        logging.debug("Listener loop stopped")
        self._callback_executor.shutdown(wait=False, cancel_futures=True)

    def add_hotkey(self, hotkey_str: str, callback: CallbackFunc) -> None:
        """
        Register a hotkey combination and its callback.

        Args:
            hotkey_str: Hotkey string (e.g., "ctrl+shift+a").
            callback: Function to call when the hotkey is pressed.

        Raises:
            HotkeyError: If the hotkey string is invalid or contains invalid keys.
        """
        key_names = [key.strip().lower() for key in hotkey_str.split('+') if key.strip()]
        if not key_names:
            raise HotkeyError("Hotkey string cannot be empty")
        scan_codes = set()
        with self._lock:
            for name in key_names:
                scan_code = self._get_scan_code(name)
                scan_codes.add(scan_code)
                if scan_code not in self._key_to_bit_index:
                    if not self._available_bit_indices:
                        raise HotkeyError("Maximum number of unique keys (64) reached")
                    bit_index = min(self._available_bit_indices)
                    self._available_bit_indices.remove(bit_index)
                    self._key_to_bit_index[scan_code] = bit_index
            target_hash = self._calculate_hash(scan_codes)
            if target_hash in self._hotkey_map:
                logging.warning(f"Overwriting callback for hotkey '{hotkey_str}' (hash={target_hash})")
            self._hotkey_map[target_hash] = callback
            logging.info(f"Registered hotkey '{hotkey_str}' (hash={target_hash})")

    def remove_hotkey(self, hotkey_str: str) -> None:
        """
        Unregister a hotkey combination.

        Args:
            hotkey_str: Hotkey string to remove (e.g., "ctrl+shift+a").

        Raises:
            HotkeyError: If the hotkey string is invalid or not registered.
        """
        key_names = [key.strip().lower() for key in hotkey_str.split('+') if key.strip()]
        if not key_names:
            raise HotkeyError("Hotkey string cannot be empty")
        scan_codes = set()
        with self._lock:
            for name in key_names:
                scan_codes.add(self._get_scan_code(name))
            target_hash = self._calculate_hash(scan_codes)
            if target_hash not in self._hotkey_map:
                raise HotkeyError(f"Hotkey '{hotkey_str}' (hash={target_hash}) not found")
            del self._hotkey_map[target_hash]
            logging.info(f"Removed hotkey '{hotkey_str}' (hash={target_hash})")

    def signal_stop(self) -> None:
        """
        Signal the listener to stop processing events and prepare for shutdown.
        Safe to call from callbacks.
        """
        with self._lock:
            if not self._stop_event.is_set():
                logging.debug("Stop signal received")
                self._stop_event.set()

    def stop(self) -> None:
        """
        Stop the listener and clean up resources.
        """
        self.signal_stop()
        if self._listener_thread.is_alive():
            logging.debug("Waiting for listener thread to stop")
            self._listener_thread.join(timeout=1.0)
            if self._listener_thread.is_alive():
                logging.warning("Listener thread did not stop within timeout")
        self._callback_executor.shutdown(wait=False, cancel_futures=True)
        logging.debug("Listener stopped")

    def __del__(self):
        """Attempt cleanup when the object is deleted."""
        self.stop()
