from pydantic import BaseModel
from typing import Literal

class LAB(BaseModel):
    L: int
    A: int
    B: int

class Mask(BaseModel):
    lower: LAB
    upper: LAB

class ROI(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int

class Comms(BaseModel):
    port: str
    baud: int

class Robot(BaseModel):
    name: str
    version: str
    comms: Comms

class Ball(BaseModel):
    lab_mask: Mask
    roi: ROI

class Goal(BaseModel):
    target_color: Literal["BLUE", "YELLOW"]
    lab_mask_yellow: Mask
    lab_mask_blue: Mask
    roi: ROI

class Config(BaseModel):
    robot: Robot
    ball: Ball
    goal: Goal