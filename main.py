from utils     import ScreenCapture
from utils     import detect_board, get_mouse_position, mouse_move_to, undo
from utils     import mouse_clip
from utils     import Listener
from utils     import Board
from threading import Thread, Event, Lock
from tkinter   import Tk
from enum      import Enum
import socket
import struct
import time


HEADER_FORMAT = '!ii'
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)

ADD_CONTENT_FORMAT   = '!ii'
ADD_CONTENT_SIZE     = struct.calcsize(ADD_CONTENT_FORMAT)

UNDO_CONTENT_FORMAT  = '!i'
UNDO_CONTENT_SIZE    = struct.calcsize(UNDO_CONTENT_FORMAT)

CLEAR_CONTENT_FORMAT = ''
CLEAR_CONTENT_SIZE   = 0


class DataType(Enum):
    UNDO  = 1
    ADD   = 2
    CLEAR = 3


class SocketClient:
    def __init__(self, host, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))

    def send(self, *args):
        """
        Sends structured data over the socket.
        Expected arguments: (DataType, content...)
        Content structure depends on DataType:
        - DataType.ADD: Expects one argument, a tuple (x, y) of integers.
        - DataType.UNDO: Expects one argument, an integer (number of undos).
        - DataType.CLEAR: Expects no content arguments.
        """
        if not args:
            print("Error: send called with no arguments.")
            return
        
        data_type_enum  = args[0]
        data_type_value = data_type_enum.value
        content_args    = args[1:]
        packed_content  = b''
        content_length  = 0
        content_format  = ''

        # Pack content based on DataType
        if data_type_enum   == DataType.ADD:
            if len(content_args) != 1 or not isinstance(content_args[0], tuple) or len(content_args[0]) != 2:
                print(f"Error: DataType.ADD requires one tuple (x, y), received {content_args}")
                return
            x, y = content_args[0]
            try:
                packed_content = struct.pack(ADD_CONTENT_FORMAT, int(x), int(y))
                content_length = ADD_CONTENT_SIZE
                content_format = ADD_CONTENT_FORMAT
            except (TypeError, ValueError) as e:
                print(f"Error: Could not pack ADD content {content_args}. {e}")
                return
        elif data_type_enum == DataType.UNDO:
            if len(content_args) != 1 or not isinstance(content_args[0], int):
                print(f"Error: DataType.UNDO requires one integer (num_undone), received {content_args}")
                return
            num_undone = content_args[0]
            try:
                packed_content = struct.pack(UNDO_CONTENT_FORMAT, num_undone)
                content_length = UNDO_CONTENT_SIZE
                content_format = UNDO_CONTENT_FORMAT
            except (TypeError, ValueError) as e:
                print(f"Error: Could not pack UNDO content {content_args}. Requires integer. {e}")
                return            
        elif data_type_enum == DataType.CLEAR:
            if len(content_args) != 0:
                print(f"Warning: DataType.CLEAR expects no content, but received {content_args}")
            content_format = CLEAR_CONTENT_FORMAT
            content_length = CLEAR_CONTENT_SIZE

        header  = struct.pack(HEADER_FORMAT, data_type_value, content_length)
        message = header + packed_content

        try:
            self.socket.sendall(message)
        except socket.error as e:
            print(f'Socket send error: {e}')
            self.socket.close()

    def receive(self):
        """
        Receives structured data from the socket.
        This method is incomplete and needs implementation to match the send format.
        It should first read the header, then read the specified content length.
        """
        try:
            header_bytes                    = self._recv_all(HEADER_SIZE)

            if not header_bytes:
                print('Receive: Connection closed or failed while reading header.')
                return None
            
            data_type_value, content_length = struct.unpack(HEADER_FORMAT, header_bytes)
            content_bytes = b''
            if content_length > 0:
                content_bytes               = self._recv_all(content_length)
                if not content_bytes:
                    print('Receive: Connection closed or failed while reading content.')
                    return None
                
            try: 
                data_type_enum              = DataType(data_type_value)
            except ValueError:
                print(f'Received unknown DataType value: {data_type_value}')
                return None
            
            return data_type_enum, content_bytes
        except struct.error as e:
            return None
        except socket.error as e:
            self.socket.close()
            return None
        
    def _recv_all(self, n):
        """Helper function to ensure all n bytes are received."""
        data = b''
        while len(data) < n:
            packet = self.socket.recv(n - len(data))
            if not packet:
                return None
            data  += packet
            time.sleep(0.01)
        return data


class Game:
    """
    Swap4 stimulate
    """
    def __init__(self, socket_client: SocketClient, board: Board):
        self.__moves                = []
        self.__client: SocketClient = socket_client
        self.__board : Board        = board
        self.__game_state           = Event()
        self.__lock_turn            = False


    def __recursive_get_move(self):
        while True:
            if (move := self.__board.get_last_move()) is not None:
                return move
            
    def background_task(self):
        while not self.__game_state.is_set():
            received_data                 = self.__client.receive()
            received_type, parsed_content = received_data

            if received_type == DataType.UNDO:
                num_undone                = parsed_content
                undo(num_undone)
                if num_undone % 2 == 0:
                    self.__lock_turn = True

            elif received_type == DataType.CLEAR:
                self.reset_game()

            time.sleep(0.1)


    def sync(self, swap2=False):        
        
        if self.__lock_turn:
            received_data                 = self.__client.receive()

            if received_data is None:
                print('Sync: Failed to receive data from server.')
                return
            
            received_type, parsed_content = received_data

            if received_data == DataType.ADD:
                move                      = parsed_content

                if move in self.__moves:
                    turn                  = len(self.__moves) - self.__moves.index(move) - 1
                    undo(turn)
                    return           

                cur_mouse_position        = get_mouse_position()
                self.__lock_turn          = False
                self.__board.click(*move)
                self.__moves.append(move)
                mouse_move_to(*cur_mouse_position)

        else:
            move               = self.__recursive_get_move()
            self.__lock_turn  ^= not swap2

            self.__moves.append(move)
            self.__client.send(DataType.ADD, move)

    def ask_swap2(self):
        # Ask Dialog: Black | White | Add 2 more stones
        if ...:
            self.__lock_turn = False
            for _ in range(2):
                self.sync(True)

    def reset_game(self):
        undo(len(self.__moves))
        return

    def swap_turn(self):
        self.__lock_turn = not self.__lock_turn

    def manager(self):
        if len(self.__moves) == 3 or len(self.__moves) == 5:
            self.ask_swap2()
        while not self.__game_state.is_set():
            self.sync()


class Controller:
    def __init__(self):
        self._screen_capture             = None
        self._detected_board             = None
        self._client_host : SocketClient = None
        self._game_manager: Game         = None
        self._board_game  : Board        = None
        
    def select_board(self):
        self._detected_board             = None
        while self._detected_board is None:       
            self._screen_capture         = ScreenCapture().get()     
            self._detected_board         = detect_board(self._screen_capture[0], self._screen_capture[2], self._screen_capture[1])    

        self._board_game                 = Board(*self._detected_board)
        mouse_clip(self._detected_board[0]                          , self._detected_board[1], 
                   self._detected_board[0] + self._detected_board[2], self._detected_board[1] + self._detected_board[3])
        
    def setup_client(self):
        host               = input('Server Host: ')
        port               = input('Port       : ')
        self._client_host  = SocketClient(host, port)

    def game_init(self):
        self._game_manager = Game(self._client_host, self._board_game)


def main():
    ...
    

if __name__ == '__main__':
    main()
