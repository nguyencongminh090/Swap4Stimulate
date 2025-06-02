from utils        import ScreenCapture
from utils        import detect_board, get_mouse_position, mouse_move_to, undo
from utils        import mouse_clip
from utils        import Listener
from utils        import Board
from threading    import Thread, Event, Lock
from enum         import Enum
import ttkbootstrap
import socket
import struct
import time



HEADER_FORMAT        = '!ii'
HEADER_SIZE          = struct.calcsize(HEADER_FORMAT)

ADD_CONTENT_FORMAT   = '!ii'
ADD_CONTENT_SIZE     = struct.calcsize(ADD_CONTENT_FORMAT)

UNDO_CONTENT_FORMAT  = '!i'
UNDO_CONTENT_SIZE    = struct.calcsize(UNDO_CONTENT_FORMAT)

SWAP_CONTENT_FORMAT  = '!?' # Boolean for turn state
SWAP_CONTENT_SIZE    = struct.calcsize(SWAP_CONTENT_FORMAT)

CLEAR_CONTENT_FORMAT = ''
CLEAR_CONTENT_SIZE   = 0


class DataType(Enum):
    UNDO  = 1
    ADD   = 2
    CLEAR = 3 
    SWAP  = 4


class SocketClient:
    def __init__(self, host, port):
        self.host           = host
        self.port           = port
        self.socket         = None
        self.__is_connected = False
        self.__lock         = Lock()
        self.connect()

    @property
    def is_connected(self) -> bool:
        """Thread-safe way to check connection status"""
        with self.__lock:
            return self.__is_connected and self.socket is not None

    def connect(self) -> bool:
        """Attempt to connect to the server."""
        with self.__lock:
            if self.__is_connected and self.socket is not None:
                return True
            
            try:
                self.socket         = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((self.host, self.port))
                self.__is_connected = True
                print(f"Connected to server at {self.host}:{self.port}")
                return True
            except Exception as e:
                print(f"Connection failed: {e}")
                self.__is_connected = False
                if self.socket:
                    try:
                        self.socket.close()
                    except:
                        pass
                self.socket = None
                return False

    def _recv_all(self, n):
        """Helper to receive exactly n bytes."""
        data = b''
        try:
            while len(data) < n:
                packet = self.socket.recv(n - len(data))
                if not packet:    # Connection closed
                    return None
                data += packet
            return data
        except socket.error:
            return None

    def send(self, *args):
        print('Sending...')
        if not self.is_connected:
            print('Not connected')
            return False
        
        try:
            if not args:
                print("Error: send called with no arguments.")
                return False
            
            data_type_enum  = args[0]
            data_type_value = data_type_enum.value
            content_args    = args[1:]
            packed_content  = b''
            content_length  = 0
            content_format  = ''

            print(f'Type: {data_type_enum} | Value: {data_type_value} | Content: {content_args[0]}')

            # Pack content based on DataType
            if data_type_enum   == DataType.ADD:
                if len(content_args) != 1 or not isinstance(content_args[0], tuple) or len(content_args[0]) != 2:
                    print(f"Error: DataType.ADD requires one tuple (x, y), received {content_args}")
                    return False
                x, y = content_args[0]
                # Validate coordinates
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                    print(f"Error: Coordinates must be numbers, received x={x}, y={y}")
                    return False
                try:
                    packed_content = struct.pack(ADD_CONTENT_FORMAT, int(x), int(y))
                    content_length = ADD_CONTENT_SIZE
                    content_format = ADD_CONTENT_FORMAT
                except (TypeError, ValueError) as e:
                    print(f"Error: Could not pack ADD content {content_args}. {e}")
                    return False
            elif data_type_enum == DataType.UNDO:
                if len(content_args) != 1 or not isinstance(content_args[0], int):
                    print(f"Error: DataType.UNDO requires one integer (num_undone), received {content_args}")
                    return False
                num_undone         = content_args[0]
                if num_undone < 0:
                    print(f"Error: Number of moves to undo must be positive, received {num_undone}")
                    return False
                try:
                    packed_content = struct.pack(UNDO_CONTENT_FORMAT, num_undone)
                    content_length = UNDO_CONTENT_SIZE
                    content_format = UNDO_CONTENT_FORMAT
                except (TypeError, ValueError) as e:
                    print(f"Error: Could not pack UNDO content {content_args}. Requires integer. {e}")
                    return False            
            elif data_type_enum == DataType.SWAP:
                if len(content_args) != 1 or not isinstance(content_args[0], bool):
                    print(f"Error: DataType.SWAP requires one boolean argument, received {content_args}")
                    return False
                turn_state         = content_args[0]
                try:
                    packed_content = struct.pack(SWAP_CONTENT_FORMAT, turn_state)
                    content_length = SWAP_CONTENT_SIZE
                    content_format = SWAP_CONTENT_FORMAT
                except (TypeError, ValueError) as e:
                    print(f"Error: Could not pack SWAP content {content_args}. {e}")
                    return False
            elif data_type_enum == DataType.CLEAR:
                if len(content_args) != 0:
                    print(f"Warning: DataType.CLEAR expects no content, but received {content_args}")
                content_format     = CLEAR_CONTENT_FORMAT
                content_length     = CLEAR_CONTENT_SIZE

            header                 = struct.pack(HEADER_FORMAT, data_type_value, content_length)
            message                = header + packed_content

            print('Message:', message)
            
            # Use sendall to ensure entire message is sent
            self.socket.sendall(message)
            print('Sent:', message)
            return True
        except socket.error as e:
            print(f'Socket send error: {e}')
            with self.__lock:
                self.__is_connected = False
                self.close()
            return False
        except Exception as e:
            print(f'Unexpected error: {e}')
            return False

    def receive(self):
        if not self.is_connected:
            return None
        
        try:
            # Do network operations outside lock
            header_bytes = self._recv_all(HEADER_SIZE)
            if not header_bytes:
                print('Connection lost while reading header.')
                with self.__lock:
                    self.__is_connected = False
                    self.close()
                return None
            
            print(f'HeaderSize: {len(header_bytes)}')
            
            data_type_value, content_length = struct.unpack(HEADER_FORMAT, header_bytes)

            print('Data:', data_type_value, content_length)
            
            # Validate content length before receiving
            if content_length < 0:
                print(f'Invalid content length: {content_length}')
                return None
            
            content_bytes = b''
            if content_length > 0:
                content_bytes = self._recv_all(content_length)
                if not content_bytes:
                    print('Receive: Connection closed or failed while reading content.')
                    with self.__lock:
                        self.__is_connected = False
                        self.close()
                    return None
                
            # Process received data outside lock
            try: 
                data_type_enum   = DataType(data_type_value)
            except ValueError:
                print(f'Received unknown DataType value: {data_type_value}')
                return None
            
            # Unpack content based on type
            unpacked_content     = None
            if data_type_enum == DataType.ADD and content_length == ADD_CONTENT_SIZE:
                unpacked_content = struct.unpack(ADD_CONTENT_FORMAT, content_bytes)
            elif data_type_enum == DataType.UNDO and content_length == UNDO_CONTENT_SIZE:
                unpacked_content = struct.unpack(UNDO_CONTENT_FORMAT, content_bytes)[0]
            elif data_type_enum == DataType.SWAP and content_length == SWAP_CONTENT_SIZE:
                unpacked_content = struct.unpack(SWAP_CONTENT_FORMAT, content_bytes)[0]
            elif data_type_enum == DataType.CLEAR:
                unpacked_content = None
            else:
                print(f'Unexpected content length {content_length} for data type {data_type_enum}')
                return None
            
            return data_type_enum, unpacked_content
        except socket.error as e:
            print(f'Socket error: {e}')
            with self.__lock:
                self.__is_connected = False
                self.close()
            return None
        except Exception as e:
            print(f'Unexpected error: {e}')
            return None

    def close(self):
        """Close socket connection safely"""
        with self.__lock:
            if self.__is_connected:
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except (socket.error, OSError):
                    pass                                      # Socket may already be closed
                try:
                    self.socket.close()
                except (socket.error, OSError):
                    pass
                self.socket         = None
                self.__is_connected = False

    def __del__(self):
        """Ensure socket is closed on deletion"""
        self.close()


class SwapDialog:
    def __init__(self):
        self.result   = None
        self.root     = ttkbootstrap.Window()
        self.root.title("Swap2 Option")
        
        # Center the dialog
        window_width  = 300
        window_height = 100
        screen_width  = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x             = (screen_width - window_width) // 2
        y             = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{50}+{x}+{y}")
        
        # Create buttons
        self.create_buttons()
        
        # Make dialog modal
        self.root.transient()
        self.root.grab_set()
        
    def create_buttons(self):
        style        = ttkbootstrap.Style()
        style.configure('Custom.TButton', padding=5)
        
        button_frame = ttkbootstrap.Frame(self.root, padding=5)
        button_frame.pack(expand=True)
        
        ttkbootstrap.Button(button_frame, text="Black", style='Custom.TButton',
                  command=lambda: self.on_click(0)).pack(side='left', padx=5, pady=5)
        ttkbootstrap.Button(button_frame, text="White", style='Custom.TButton',
                  command=lambda: self.on_click(1)).pack(side='left', padx=5, pady=5)
        ttkbootstrap.Button(button_frame, text="Add 2 moves", style='Custom.TButton',
                  command=lambda: self.on_click(2)).pack(side='left', padx=5, pady=5)
        
    def on_click(self, value):
        self.result = value
        self.root.quit()
        self.root.destroy()
        
    def show(self):
        self.root.mainloop()
        return self.result


class Game:
    """
    Swap4 stimulate with improved state management
    """
    def __init__(self, socket_client: SocketClient, board: Board):
        self.__moves                           = []
        self.__client           : SocketClient = socket_client
        self.__board            : Board        = board
        self.__listener         : Listener     = Listener()
        self.__game_state                      = Event()
        self.__lock_turn                       = False if input('B/W').lower() == 'b' else True    
        self.__new_game                        = True
        self.__swap_pending                    = False
        self.__moves_until_swap                = 3
        self.__lock                            = Lock()                                              # Add dedicated lock for thread safety
        self.__background_thread: Thread       = Thread(target=self.background_task, daemon=True)
        self.__is_running                      = True

    def __recursive_get_move(self):
        while self.__is_running:                                                                     # Add timeout and interruption check
            if (move := self.__board.get_last_move()) is not None:
                return move
            time.sleep(0.05)                                                                         # Add small sleep to prevent CPU spinning
        return None
            
    def background_task(self):
        while not self.__game_state.is_set() and self.__is_running:
            try:
                # Do network operations outside of lock
                received_data = self.__client.receive()
                if received_data is None:
                    time.sleep(0.1)  # Add small delay to prevent CPU spinning
                    continue

                received_type, parsed_content = received_data

                # Only acquire lock for state modifications
                if received_type == DataType.UNDO:
                    num_undone = parsed_content
                    undo(num_undone)
                    
                    if len(self.__moves) <= self.__moves_until_swap:
                        self.__swap_pending = False
                    
                    if num_undone % 2 == 0:
                        self.__lock_turn = True

                elif received_type == DataType.CLEAR:
                    self.reset_game()
                        
                elif received_type == DataType.SWAP:
                    self.__lock_turn = parsed_content
                    print(f"Turn swapped by opponent. Your turn: {not self.__lock_turn}")

            except Exception as e:
                print(f"Error in background task: {e}")
                if not self.__is_running:
                    break
                time.sleep(0.1)

    def stop(self):
        """Stop all threads and cleanup resources"""
        self.__is_running = False
        self.__game_state.set()
        if self.__background_thread.is_alive():
            self.__background_thread.join(timeout=1.0)
        if self.__listener:
            self.__listener.stop()

    def __del__(self):
        """Ensure cleanup on deletion"""
        self.stop()

    def sync(self, swap2=False):    
        print('Sync')    
        if self.__lock_turn:
            # Get data outside lock
            print('---Get Data---')
            received_data = self.__client.receive()
            print('---Raw Data---', received_data)
            if received_data is None:
                print('Sync: Failed to receive data from server.')
                return
            
            received_type, parsed_content = received_data
            print(f'Received Data: {received_data}')


            if received_type == DataType.ADD:
                move     = parsed_content
                if move in self.__moves:
                    turn = len(self.__moves) - self.__moves.index(move) - 1
                    undo(turn)
                    return           

                cur_mouse_position = get_mouse_position()
                self.__lock_turn = False
                self.__board.click(*self.__board.move_to_coord(*move))
                self.__moves.append(move)
                mouse_move_to(*cur_mouse_position)
        else:
            print('Lock Release')
            # Get move outside lock
            move = self.__recursive_get_move()

            if move and move not in self.__moves:
                print(f'Append {move} | Len: {len(self.__moves)}')
                self.__moves.append(move)
            
                self.__lock_turn ^= not swap2
                    
                # Send data outside lock 
                status = self.__client.send(DataType.ADD, move)
                print('Send Status:', status)
                
                if not swap2 and len(self.__moves) == self.__moves_until_swap:
                    self.__swap_pending = True

    def ask_swap2(self):
        if not self.__swap_pending:
            print("Swap2 option not available at this time")
            return
            
        dialog                      = SwapDialog()
        result                      = dialog.show()
        
        self.__swap_pending         = False                                                          # Reset swap pending state
        
        if result == 2:                                                                              # Add 2 more stones
            self.__lock_turn        = False
            self.__moves_until_swap = 5                                                              # Next swap opportunity after 2 more moves
            for _ in range(2):
                self.sync(True)
        else:                                                                                        # Chose black (0) or white (1)
            self.__lock_turn        = result == 0                                                    # True if black, False if white
            self.__client.send(DataType.SWAP, not self.__lock_turn)                                  # Send opposite turn to opponent
        
        return

    def reset_game(self):
        """Reset the game state completely"""
        undo(len(self.__moves))
        self.__moves.clear()
        self.__new_game             = True
        self.__swap_pending         = False
        self.__moves_until_swap     = 3
        self.__lock_turn            = False
        self.__client.send(DataType.CLEAR)

    def swap_turn(self):
        """Manually swap turns and notify opponent"""
        self.__lock_turn            = not self.__lock_turn
        self.__client.send(DataType.SWAP, not self.__lock_turn)

    def manager(self):
        """Main game loop with improved state management"""
        print('Manager Start')
        print('PlayerTurn:', self.__lock_turn)
        while not self.__game_state.is_set():
            if self.__new_game:
                self.__new_game = False
                self.__moves_until_swap = 3
                
            if len(self.__moves) < 3:
                self.sync(True)
            elif self.__swap_pending:
                self.ask_swap2()
            else:
                self.sync()

    def start(self):
        with self.__listener as listener:
            try:
                listener.add_hotkey('alt+w', self.swap_turn)
                listener.add_hotkey('alt+r', self.reset_game)
                listener.add_hotkey('alt+p', self.manager)
    
                # self.__background_thread.start()

                while not listener._stop_event.is_set():
                    time.sleep(0.1)
            except Exception as e:
                print(f'Error: {e}')


class Controller:
    def __init__(self):
        self._screen_capture             = None
        self._detected_board             = None
        self._client_host : SocketClient = None
        self._game_manager: Game         = None
        self._board_game  : Board        = None
        self._listener    : Listener     = None
        self._is_running  : bool         = False

    def select_board(self):
        try:
            self._detected_board             = None
            while self._detected_board is None:       
                self._screen_capture         = ScreenCapture().get()     
                self._detected_board         = detect_board(self._screen_capture[0], self._screen_capture[2], self._screen_capture[1])    
                if None in self._detected_board:
                    self._detected_board     = None
            
            self._board_game                 = Board((self._detected_board[0], self._detected_board[1]),
                                                     (self._detected_board[2], self._detected_board[3]), 15, 15)
            # mouse_clip(self._detected_board[0]                          , self._detected_board[1], 
            #            self._detected_board[0] + self._detected_board[2], self._detected_board[1] + self._detected_board[3])
        except Exception as e:
            print(f"Error selecting board: {e}")
            self.cleanup()
            raise

    def setup_client(self):
        try:
            host               = input('Server Host: ')
            port               = int(input('Port: '))
            if not (0 <= port <= 65535):
                raise ValueError("Port must be between 0-65535")
            self._client_host  = SocketClient(host, port)
        except ValueError as e:
            print(f"Invalid port number: {e}")
            self.cleanup()
            raise
        except Exception as e:
            print(f"Error setting up client: {e}")
            self.cleanup()
            raise

    def game_init(self):
        try:
            if not self._client_host or not self._board_game:
                raise RuntimeError("Client and board must be initialized first")
            self._game_manager = Game(self._client_host, self._board_game)
            return self._game_manager
        except Exception as e:
            print(f"Error initializing game: {e}")
            self.cleanup()
            raise

    def init_game(self):
        """
        Initialize the game with hotkey setup, board selection, and client connection.
        This function handles the complete setup process including error handling.
        """
        try:
            self._is_running = True
            self._listener   = Listener()

            # Setup hotkey for board selection
            def on_board_select():
                if self._client_host is None:
                    self.setup_client()
                self.select_board()
                # After board selection, initialize and start the game
                if self._board_game and self._client_host:
                    game     = self.game_init()
                    if game:
                        game.start()

            # Register hotkey for board selection (Alt+B)
            self._listener.add_hotkey('alt+b', on_board_select)

            # Start listening for hotkeys
            print("Press Alt+B to select the game board and start...")
            while self._is_running:
                if self._listener._stop_event.is_set():
                    break
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\nGame initialization interrupted by user.")
            self.cleanup()
        except Exception as e:
            print(f"Error during game initialization: {e}")
            self.cleanup()
            raise
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up all resources"""
        try:
            # Release mouse clip
            mouse_clip(0, 0, 0, 0)
            
            # Stop listener
            if self._listener:
                self._listener.stop()
                self._listener     = None
            
            # Stop game manager
            if self._game_manager:
                self._game_manager.stop()
                self._game_manager = None
            
            # Close socket connection
            if self._client_host:
                self._client_host.close()
                self._client_host  = None
                
            # Clear other resources
            self._board_game       = None
            self._detected_board   = None
            self._screen_capture   = None
            self._is_running       = False
            
        except Exception as e:
            print(f"Error during cleanup: {e}")

    def __enter__(self):
        """Support context manager pattern"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure cleanup on context exit"""
        self.cleanup()

    def __del__(self):
        """Ensure cleanup on deletion"""
        self.cleanup()


def main():
    try:
        with Controller() as controller:
            print("Welcome to Swap4!")
            print("Controls:")
            print("- Alt+B: Select game board and start")
            print("- Alt+W: Swap turn")
            print("- Alt+R: Reset game")
            print("- Alt+P: Play/Continue game")
            print("- ESC: Exit")
            
            controller.init_game()
    except KeyboardInterrupt:
        print("\nGame terminated by user.")
    except Exception as e:
        print(f"Fatal error: {e}")


if __name__ == '__main__':
    main()
