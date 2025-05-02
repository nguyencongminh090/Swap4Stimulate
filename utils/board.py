import time
import win32api
import win32con
from typing import Tuple, List, Optional
from utils  import get_pixel


def valid(move: str, size_x: int = 15, size_y: int = 15) -> bool:
    """
    Check if a move string is valid for the grid.

    Args:
        move: Move string (e.g., 'a1', 'b15').
        size_x: Grid width (number of columns).
        size_y: Grid height (number of rows).

    Returns:
        True if the move is valid, False otherwise.
    """
    if len(move) < 2 or not move[0].isalpha() or not move[1:].isnumeric():
        return False
    try:
        x, y = convert_move(move, size_y)
        return 0 <= x < size_x and 0 <= y < size_y
    except ValueError:
        return False


def convert_move(move: str, size_y: int = 15) -> Tuple[int, int]:
    """
    Convert a move string to grid coordinates.

    Args:
        move: Move string (e.g., 'a1', 'b15').
        size_y: Grid height (number of rows).

    Returns:
        Tuple of (x, y) coordinates.

    Raises:
        ValueError: If move is invalid (e.g., non-letter prefix, non-numeric suffix).
    """
    if not move or not move[0].isalpha() or not move[1:].isnumeric():
        raise ValueError(f"Invalid move format: '{move}'")
    return ord(move[0].lower()) - 97, size_y - int(move[1:])


def get(move_string: str, size_x: int = 15, size_y: int = 15) -> List[Tuple[int, int]]:
    """
    Parse a string of moves into a list of coordinates.

    Args:
        move_string: String of concatenated moves (e.g., 'a1b2c3').
        size_x: Grid width (number of columns).
        size_y: Grid height (number of rows).

    Returns:
        List of (x, y) coordinate tuples for valid moves.
    """
    moves = []
    i     = 0
    while i < len(move_string):
        # Extract letter
        if i >= len(move_string) or not move_string[i].isalpha():
            i += 1
            continue
        letter = move_string[i]
        i += 1
        # Extract number
        number = ""
        while i < len(move_string) and move_string[i].isdigit():
            number += move_string[i]
            i += 1
        move = letter + number
        if valid(move, size_x, size_y):
            moves.append(convert_move(move, size_y))
    return moves


class Board:
    """
    Simulates mouse clicks on a grid for board interactions.

    Maps move strings (e.g., 'a1') to screen coordinates based on a top-left point
    and grid size, performing clicks for valid moves.
    """
    def __init__(self, point: Tuple[int, int], size: Tuple[int, int], size_x: int, size_y: int):
        """
        Initialize the board with grid geometry.

        Args:
            point: Top-left corner (x, y) of the grid.
            size: Grid dimensions (width, height) in pixels.
            size_x: Number of columns.
            size_y: Number of rows.

        Raises:
            ValueError: If size_x, size_y, or size are invalid.
        """
        if size_x < 1 or size_y < 1:
            raise ValueError("Grid dimensions must be positive")
        if size[0] <= 0 or size[1] <= 0:
            raise ValueError("Grid size must be positive")

        self.__x1       = point[0]
        self.__y1       = point[1]
        self.__w        = size[0]
        self.__h        = size[1]
        self.__size_x   = size_x
        self.__size_y   = size_y
        self.__dis_x    = self.__w / (size_x - 1) if size_x > 1 else 0
        self.__dis_y    = self.__h / (size_y - 1) if size_y > 1 else 0

    def click(self, x: int, y: int) -> None:
        """
        Simulate a left mouse click at the given screen coordinates.

        Args:
            x: Screen x-coordinate.
            y: Screen y-coordinate.

        Raises:
            RuntimeError: If clicking is not supported on the platform.
        """
        try:
            win32api.SetCursorPos((round(x), round(y)))
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
        except Exception as e:
            raise RuntimeError(f"Failed to simulate click at ({x}, {y}): {e}")

    def move_to_coord(self, x: int, y: int) -> Tuple[int, int]:
        """
        Convert grid coordinates to screen coordinates.

        Args:
            x: Grid x-coordinate (column).
            y: Grid y-coordinate (row).

        Returns:
            Tuple of (screen_x, screen_y) coordinates.
        """
        screen_x    = self.__x1 + round(x * self.__dis_x)
        screen_y    = self.__y1 + round((14 - y) * self.__dis_y)
        return screen_x, screen_y

    def set_pos(self, move_string: str) -> None:
        """
        Simulate clicks for a string of moves.

        Args:
            move_string: String of moves (e.g., 'a1b2c3').
        """
        moves = get(move_string, self.__size_x, self.__size_y)
        for move in moves:
            self.click(*self.move_to_coord(*move))

    def get_last_move(self) -> Tuple[int, int] | None:
        """
        Return last move on board
        """
        for y in range(15):
            for x in range(15):
                coord = self.move_to_coord(x, 14 - y)
                if get_pixel(*coord) == (255, 0, 0):
                    return coord