import cv2
import mss
import numpy as np
import tkinter as tk
from ctypes import windll
from PIL    import Image, ImageTk
from typing import Tuple, Optional


def dark_image(image: np.ndarray, alpha: float = 1.0) -> np.ndarray:
    """
    Apply a darkening filter to an image by scaling pixel values.

    Args:
        image: Input image as a numpy array (e.g., RGB uint8).
        alpha: Scaling factor (0.0 to 1.0 darkens, >1.0 brightens).

    Returns:
        Darkened image as a numpy array.

    Raises:
        ValueError: If image is invalid or alpha is negative.
    """
    if not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("Input image must be a non-empty numpy array")
    if alpha < 0:
        raise ValueError("Alpha must be non-negative")

    kernel      = np.array([[0,   0,   0],
                            [0, alpha, 0],
                            [0,   0,   0]])
    result      = cv2.filter2D(image, -1, kernel)
    return result


def get_screen_size():
    user32 = windll.user32
    return user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)


class ScreenCapture(tk.Toplevel):
    """
    A Tkinter-based screen capture utility for selecting a region by dragging a rectangle.

    Displays a darkened screenshot, allows rectangle selection, and returns the cropped image
    with top-left coordinates.
    """
    def __init__(self):
        """Initialize screen capture window with proper root window management."""
        self.root       = tk.Tk()
        self.root.withdraw()  # Hide the root window
        super().__init__(self.root)  # Initialize Toplevel with root as parent
        
        self.sct        = mss.mss()
        self.__w        = 0
        self.__h        = 0
        self.__start_x  = None
        self.__start_y  = None
        self.__rect     = None
        self.__img      = None
        self.__img_tk   = None

        self.__w, self.__h = get_screen_size()
        self.attributes('-topmost', True)
        self.geometry(f"{self.__w}x{self.__h}")
        self.overrideredirect(True)

        self.canvas = tk.Canvas(
            self,
            bg                 = 'white',
            highlightthickness = 0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        monitor     = self.sct.monitors[1]  # Primary monitor
        screenshot  = np.array(self.sct.grab(monitor))
        self.__img  = cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)
        darkened    = dark_image(self.__img, 0.6)
        self.__img_tk = ImageTk.PhotoImage(Image.fromarray(darkened))
        self.canvas.create_image(0, 0, image=self.__img_tk, anchor='nw')

        self.canvas.bind('<ButtonPress-1>',   self.__on_mouse_press)
        self.canvas.bind('<B1-Motion>',       self.__on_mouse_hold)
        self.canvas.bind('<ButtonRelease-1>', self.__on_mouse_release)

    def __on_mouse_press(self, event: tk.Event) -> None:
        """
        Handle mouse press to start rectangle selection.

        Args:
            event: Tkinter event with mouse coordinates.
        """
        self.__start_x = event.x
        self.__start_y = event.y

    def __on_mouse_hold(self, event: tk.Event) -> None:
        """
        Handle mouse drag to draw the selection rectangle.

        Args:
            event: Tkinter event with mouse coordinates.
        """
        if self.__start_x is None or self.__start_y is None:
            return
        if self.__rect:
            self.canvas.delete(self.__rect)
        self.__rect = self.canvas.create_rectangle(
            self.__start_x,
            self.__start_y,
            event.x,
            event.y,
            outline = '#ffffff',
            width   = 3
        )

    def __on_mouse_release(self, event: tk.Event) -> None:
        """
        Handle mouse release to finalize the selection and capture the region.

        Args:
            event: Tkinter event with mouse coordinates.
        """
        x1 = min(self.__start_x, event.x)
        y1 = min(self.__start_y, event.y)
        x2 = max(self.__start_x, event.x)
        y2 = max(self.__start_y, event.y)

        self.__start_x = x1
        self.__start_y = y1

        self.canvas.delete("all")
        self.after(100, self.__screenshot, x1, y1, x2, y2)

    def __screenshot(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Crop the selected region and quit."""
        if x2 <= x1 or y2 <= y1:
            self.__img = np.array([])
        else:
            self.__img = self.__img[y1:y2, x1:x2]
        self.__img_tk = None
        self.quit()

    def get(self) -> Tuple[np.ndarray, int, int]:
        """Run window and return captured data."""
        self.mainloop()
        self.destroy()        # Destroy the Toplevel window
        self.root.destroy()   # Destroy the root window
        return self.__img, self.__start_x, self.__start_y