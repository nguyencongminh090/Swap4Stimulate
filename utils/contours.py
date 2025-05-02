import cv2
import numpy as np
from scipy.spatial import KDTree
from typing        import List, Tuple, Optional


class UnionFind:
    """
    Disjoint-set data structure for efficient grouping operations.
    """
    def __init__(self, n: int):
        """
        Initialize UnionFind with n elements.

        Args:
            n: Number of elements in the disjoint-set.
        """
        self.parent = list(range(n))
        self.rank   = [0] * n

    def find(self, x: int) -> int:
        """
        Find the root of element x with path compression.

        Args:
            x: Element to find.

        Returns:
            Root of the set containing x.
        """
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])  # Path compression
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        """
        Merge the sets containing elements x and y.

        Args:
            x: First element.
            y: Second element.
        """
        px = self.find(x)
        py = self.find(y)
        if px == py:
            return
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1


def group_overlapping_contours(
    contours         : List,
    distanceThreshold: float                     = 10.0,
    areaSize         : float                     = 300.0,
    useConvexHull    : bool                      = False,
    useMasks         : bool                      = False,
    imageShape       : Optional[Tuple[int, int]] = None
) -> List:
    """
    Group overlapping or nearby contours efficiently.

    Args:
        contours: List of contours from cv2.findContours.
        distanceThreshold: Max distance between contour centers to consider them related.
        areaSize: Minimum contour area to filter noise.
        useConvexHull: If True, merge grouped contours into a convex hull; else, concatenate points.
        useMasks: If True, use pixel-level overlap detection (requires imageShape).
        imageShape: Tuple (height, width) of the image, required if useMasks=True.

    Returns:
        List of grouped contours.

    Raises:
        ValueError: If imageShape is None when useMasks=True.
    """
    # Filter contours by area to remove noise
    significant_contours = [cnt for cnt in contours if cv2.contourArea(cnt) >= areaSize]
    if not significant_contours:
        return []

    # Initialize variables
    n                 = len(significant_contours)
    bounding_rects    = [cv2.boundingRect(cnt) for cnt in significant_contours]
    centers           = np.array([(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2) for rect in bounding_rects])
    uf                = UnionFind(n)

    # Create masks for pixel-level overlap if needed
    if useMasks:
        if imageShape is None:
            raise ValueError("imageShape must be provided when useMasks=True")
        masks = [np.zeros(imageShape, dtype=np.uint8) for _ in range(n)]
        for i, cnt in enumerate(significant_contours):
            cv2.drawContours(masks[i], [cnt], -1, 255, thickness=cv2.FILLED)

    # Build KDTree for efficient neighbor queries
    tree = KDTree(centers)

    # Group contours based on proximity or overlap
    for i in range(n):
        rect1   = bounding_rects[i]
        center1 = centers[i]
        indices = tree.query_ball_point(center1, distanceThreshold + max(rect1[2], rect1[3]))

        for j in indices:
            if i >= j or uf.find(i) == uf.find(j):
                continue
            rect2         = bounding_rects[j]
            x_overlap     = max(0, min(rect1[0] + rect1[2], rect2[0] + rect2[2]) - max(rect1[0], rect2[0]))
            y_overlap     = max(0, min(rect1[1] + rect1[3], rect2[1] + rect2[3]) - max(rect1[1], rect2[1]))
            rects_overlap = x_overlap > 0 and y_overlap > 0
            distance      = np.linalg.norm(center1 - centers[j]) if not rects_overlap else 0
            pixel_overlap = False

            if useMasks and (rects_overlap or distance <= distanceThreshold):
                overlap_mask  = cv2.bitwise_and(masks[i], masks[j])
                pixel_overlap = np.any(overlap_mask)

            if rects_overlap or pixel_overlap or (distance > 0 and distance <= distanceThreshold):
                uf.union(i, j)

    # Collect grouped contours
    groups = {}
    for idx in range(n):
        root = uf.find(idx)
        if root not in groups:
            groups[root] = []
        groups[root].append(significant_contours[idx])

    # Merge contours in each group
    grouped_contours = [
        cv2.convexHull(np.vstack(group)) if useConvexHull else np.vstack(group)
        for group in groups.values()
    ]
    return grouped_contours