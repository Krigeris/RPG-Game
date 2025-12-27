from typing import List, Tuple

import pygame

from .utils import Clamp


class Button:
    def __init__(self, Rect: pygame.Rect, Text: str):
        self.Rect = Rect
        self.Text = Text
        self.Hovered = False

    def Draw(self, Surface, Font, Color=(235, 235, 235), HoverColor=(255, 255, 255)):
        pygame.draw.rect(Surface, (40, 40, 40), self.Rect, border_radius=8)
        pygame.draw.rect(Surface, (90, 90, 90), self.Rect, width=2, border_radius=8)
        Txt = Font.render(self.Text, True, HoverColor if self.Hovered else Color)
        Surface.blit(Txt, Txt.get_rect(center=self.Rect.center))

    def HandleMotion(self, Pos):
        self.Hovered = self.Rect.collidepoint(Pos)

    def HandleClick(self, Pos) -> bool:
        return self.Rect.collidepoint(Pos)


class Tooltip:
    def __init__(self):
        self.TextLines: List[str] = []
        self.Visible = False
        self.Pos = (0, 0)

    def Show(self, Pos: Tuple[int, int], Lines: List[str]):
        self.Visible = True
        self.Pos = Pos
        self.TextLines = Lines

    def Hide(self):
        self.Visible = False

    def Draw(self, Surface, Font):
        if not self.Visible or not self.TextLines:
            return
        Padding = 8
        LineSurfs = [Font.render(L, True, (240, 240, 240)) for L in self.TextLines]
        W = max(s.get_width() for s in LineSurfs) + Padding * 2
        H = sum(s.get_height() for s in LineSurfs) + Padding * 2
        X, Y = self.Pos
        X = Clamp(X + 16, 0, Surface.get_width() - W - 4)
        Y = Clamp(Y + 16, 0, Surface.get_height() - H - 4)
        Rect = pygame.Rect(int(X), int(Y), int(W), int(H))
        pygame.draw.rect(Surface, (18, 18, 18), Rect, border_radius=10)
        pygame.draw.rect(Surface, (120, 120, 120), Rect, width=2, border_radius=10)
        Ty = Rect.y + Padding
        for S in LineSurfs:
            Surface.blit(S, (Rect.x + Padding, Ty))
            Ty += S.get_height()
