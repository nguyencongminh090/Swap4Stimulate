import cv2
import numpy as np
import mss
import win32gui
import win32api
import win32con


class CustomArr:
    def __init__(self):
        self.__data = []

    def __setitem__(self, index, value):
        if index >= len(self.__data):
            self.__data.extend([None] * (index - len(self.__data) + 1))
        self.__data[index] = value

    def __getitem__(self, index):
        return self.__data[index]
    
    def __iter__(self):
        return iter(self.__data)
    
    def __repr__(self):
        return repr(self.__data)
    

class ArrangedArr:
    def __init__(self):
        self.__data: CustomArr = CustomArr()
        self.__bIndex = 0
        self.__wIndex = 1

    def add(self, move, label):
        if label.lower() == 'b':
            self.__data[self.__bIndex] = move
            self.__bIndex += 2
        elif label.lower() == 'w':
            self.__data[self.__wIndex] = move
            self.__wIndex += 2

    def get(self):
            return self.__data


def img_crop(image, x1, y1, h, w):
    """
    Crop an image to the specified coordinates.

    Args:
        image: The image to crop.
        x1: The x-coordinate of the top-left corner.
        y1: The y-coordinate of the top-left corner.
        x2: The x-coordinate of the bottom-right corner.
        y2: The y-coordinate of the bottom-right corner.

    Returns:
        Cropped image.
    """
    return image[y1:y1+h, x1:x1+w]

def screenshot():
    """
    Capture a screenshot of the entire primary monitor.

    Returns:
        numpy.ndarray: The captured screenshot as an RGB image.
    """
    sct   = mss.mss()
    image = cv2.cvtColor(np.array(sct.grab(sct.monitors[0])), cv2.COLOR_BGR2RGB)
    return image


def screenshot_region(x1, y1, h, w):
    """
    Capture a screenshot of a specific region of the primary monitor.

    Args:
        x1 (int): The x-coordinate of the top-left corner of the region.
        y1 (int): The y-coordinate of the top-left corner of the region.
        h  (int): The height of the region.
        w  (int): The width of the region.

    Returns:
        numpy.ndarray: The captured screenshot of the specified region as an RGB image.
    """
    image = screenshot()
    image = image[y1:y1 + h, x1:x1 + w]
    return image


def get_pixel(x, y):
    """
    Get color of pixel -> RGB
    """
    hdc = win32gui.GetDC(0)
    if hdc:
        try:
            pixel_color_bgr = win32gui.GetPixel(hdc, x, y)
            red   = (pixel_color_bgr >> 16) & 0xFF
            green = (pixel_color_bgr >> 8)  & 0xFF
            blue  = pixel_color_bgr         & 0xFF
            return (red, green, blue)
        finally:
            win32gui.ReleaseDC(0, hdc)
    else:
        return None
    

def get_mouse_position():
    return win32api.GetCursorPos()


def mouse_clip(left= 0, top=0, right=0, bottom=0):
    win32api.ClipCursor((left, top, right, bottom))


def mouse_move_to(x, y):
    win32api.SetCursorPos((x, y))


def undo(repeat=1):
    for i in range(repeat):
        win32api.keybd_event(win32con.VK_LEFT, 0, 0, 0)
        win32api.keybd_event(win32con.VK_LEFT, 0, win32con.KEYEVENTF_KEYUP, 0)


def redo(repeat=1):
    for i in range(repeat):
        win32api.keybd_event(win32con.VK_RIGHT, 0, 0, 0)
        win32api.keybd_event(win32con.VK_RIGHT, 0, win32con.KEYEVENTF_KEYUP, 0)
