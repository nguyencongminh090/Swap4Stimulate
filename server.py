import socket
import struct
import logging
import threading
import argparse
from   enum   import Enum
from   typing import Dict, Tuple, Optional, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("server.log")
    ]
)

# Protocol Constants (matching client protocol)
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


class GameState:
    """Manages the state of a game between two players."""
    def __init__(self):
        self.moves       : List[Tuple[int, int]] = []
        self.current_turn: bool                  = False     # False = first player, True = second player

    def add_move(self, x: int, y: int) -> None:
        """Add a move to the game state."""
        self.moves.append((x, y))
        self.current_turn                        = not self.current_turn

    def undo_moves(self, num_moves: int) -> None:
        """Remove the last n moves from the game state."""
        for _ in range(min(num_moves, len(self.moves))):
            self.moves.pop()
        # Adjust turn based on number of moves
        self.current_turn                        = bool(len(self.moves) % 2)

    def clear(self) -> None:
        """Reset the game state."""
        self.moves.clear()
        self.current_turn                        = False


class ClientHandler:
    """Handles communication with a single client."""
    def __init__(self, sock: socket.socket, addr: Tuple[str, int], game: GameState, server: 'GameServer'):
        self.sock    = sock
        self.addr    = addr
        self.game    = game
        self.server  = server
        self.running = True

    def _recv_all(self, n: int) -> Optional[bytes]:
        """Helper to receive exactly n bytes."""
        data = b''
        try:
            while len(data) < n and self.running:
                packet = self.sock.recv(n - len(data))
                if not packet:                             # Connection closed by client
                    return None
                data  += packet
            return data if self.running else None
        except Exception:                                  # Any socket error
            return None

    def _send_message(self, data_type: DataType, content: bytes = b'') -> bool:
        """Send a message to the client with proper protocol formatting."""
        try:
            header = struct.pack(HEADER_FORMAT, data_type.value, len(content))
            self.sock.sendall(header + content)
            return True
        except Exception as e:
            logging.error(f"Error sending message to {self.addr}: {e}")
            return False

    def handle_client(self) -> None:
        """Main client handling loop."""
        logging.info(f"New connection from {self.addr}")
        
        try:
            while self.running:
                # Read header
                header_data = self._recv_all(HEADER_SIZE)
                if not header_data:
                    logging.info(f"Client {self.addr} disconnected")
                    break

                data_type_value, content_length = struct.unpack(HEADER_FORMAT, header_data)

                # Read content if any
                content = self._recv_all(content_length) if content_length > 0 else b''
                if content_length > 0 and not content:
                    logging.info(f"Client {self.addr} disconnected during content read")
                    break

                try:
                    data_type = DataType(data_type_value)
                except ValueError:
                    logging.error(f"Invalid data type received: {data_type_value}")
                    continue

                # Handle message based on type and broadcast to other players
                if data_type == DataType.ADD and content_length == ADD_CONTENT_SIZE:
                    x, y = struct.unpack(ADD_CONTENT_FORMAT, content)
                    self.game.add_move(x, y)
                    logging.info(f"Move added at ({x}, {y})")
                    self.server.broadcast(self.addr, data_type, content)

                elif data_type == DataType.UNDO and content_length == UNDO_CONTENT_SIZE:
                    num_moves = struct.unpack(UNDO_CONTENT_FORMAT, content)[0]
                    self.game.undo_moves(num_moves)
                    logging.info(f"Undid {num_moves} moves")
                    self.server.broadcast(self.addr, data_type, content)

                elif data_type == DataType.SWAP and content_length == SWAP_CONTENT_SIZE:
                    new_turn = struct.unpack(SWAP_CONTENT_FORMAT, content)[0]
                    self.game.current_turn = new_turn
                    logging.info(f"Turn swapped, current turn: {new_turn}")
                    self.server.broadcast(self.addr, data_type, content)

                elif data_type == DataType.CLEAR:
                    self.game.clear()
                    logging.info("Game cleared")
                    self.server.broadcast(self.addr, data_type, content)

        except Exception as e:
            logging.error(f"Error handling client {self.addr}: {e}")
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Clean up resources used by this client handler."""
        if not self.running:  # Already cleaned up
            return
            
        self.running = False
        try:
            self.sock.close()
        except Exception as e:
            logging.error(f"Error closing socket for {self.addr}: {e}")
        
        # Make sure we're removed from server's client list
        self.server.remove_client(self.addr)
        logging.info(f"Connection closed for {self.addr}")


class GameServer:
    """Main server class that accepts connections and manages games."""
    def __init__(self, host: str = 'localhost', port: int  = 8888):
        self.host                                          = host
        self.port                                          = port
        self.sock                                          = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.running                                       = False
        self.clients: Dict[Tuple[str, int], ClientHandler] = {}
        self.game_state                                    = GameState()
        self._lock                                         = threading.Lock()  # Add lock for thread-safe broadcasting

    def remove_client(self, addr: Tuple[str, int]) -> None:
        """Remove a client from the server's client list."""
        with self._lock:
            if addr in self.clients:
                del self.clients[addr]
                logging.info(f"Removed client {addr}. Total clients: {len(self.clients)}")

    def broadcast(self, sender_addr: Tuple[str, int], data_type: DataType, content: bytes = b'') -> None:
        """Broadcast a message to all clients except the sender."""
        print('Broadcast Called')
        with self._lock:
            disconnected = []
            for addr, client in self.clients.items():
                if addr != sender_addr:  # Don't send back to sender
                    try:
                        if not client._send_message(data_type, content):
                            disconnected.append(addr)
                    except Exception as e:
                        logging.error(f"Error broadcasting to {addr}: {e}")
                        disconnected.append(addr)
            
            # Remove disconnected clients
            for addr in disconnected:
                self.remove_client(addr)

    def start(self) -> None:
        """Start the server."""
        try:
            self.sock.bind((self.host, self.port))
            self.sock.listen(2)  # Only allow 2 connections for a 2-player game
            self.running = True
            logging.info(f"Server started on {self.host}:{self.port}")

            while self.running:
                try:
                    client_socket, addr = self.sock.accept()
                    if len(self.clients) >= 2:
                        logging.warning(f"Rejected connection from {addr}: Game full")
                        client_socket.close()
                        continue

                    handler            = ClientHandler(client_socket, addr, self.game_state, self)
                    self.clients[addr] = handler
                    
                    # Start client handler in a new thread
                    thread             = threading.Thread(target=handler.handle_client)
                    thread.daemon      = True
                    thread.start()

                    logging.info(f"Client {addr} connected. Total clients: {len(self.clients)}")

                except Exception as e:
                    logging.error(f"Error accepting connection: {e}")

        except Exception as e:
            logging.error(f"Server error: {e}")
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Clean up server resources."""
        self.running = False
        
        # Clean up client connections
        for handler in self.clients.values():
            handler.cleanup()
        self.clients.clear()

        # Close server socket
        try:
            self.sock.close()
        except Exception as e:
            logging.error(f"Error closing server socket: {e}")
        
        logging.info("Server shutdown complete")


def main():
    
    parser = argparse.ArgumentParser(description="Swap4 Game Server")
    parser.add_argument('--host', default='localhost', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8888, help='Port to bind to')
    
    args   = parser.parse_args()
    
    server = GameServer(args.host, args.port)
    try:
        server.start()
    except KeyboardInterrupt:
        logging.info("Server shutdown requested")
        server.cleanup()


if __name__ == '__main__':
    main()