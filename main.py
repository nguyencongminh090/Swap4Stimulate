from utils     import ScreenCapture
from utils     import detect_board, get_mouse_position, mouse_move_to, undo
from utils     import mouse_clip
from utils     import Listener
from utils     import Board
from threading import Thread, Event, Lock
from tkinter   import Tk


class SocketClient:
    def __init__(self):
        ...

    def send():
        ...

    def receive():
        ...


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


    def sync(self, swap2=False):        
        
        if self.__lock_turn:
            move               = self.__client.receive()

            if move in self.__moves:
                turn           = len(self.__moves) - self.__moves.index(move) - 1
                undo(turn)
                return           

            cur_mouse_position = get_mouse_position()
            self.__lock_turn   = False

            self.__board.click(*move)
            self.__moves.append(move)
            mouse_move_to(*cur_mouse_position)
        else:
            move             = self.__recursive_get_move()
            self.__lock_turn ^= not swap2

            self.__moves.append(move)
            self.__client.send(..., move)

    def ask_swap2(self):
        # Ask Dialog
        if ...:
            self.__lock_turn = False
            for _ in range(2):
                self.sync(True)

    def reset_game(self):
        ...

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
        ...

    def game_init(self):
        self._game_manager = Game(self._client_host, )


def main():

    screen_capture = ScreenCapture().get()
    

if __name__ == '__main__':
    main()
