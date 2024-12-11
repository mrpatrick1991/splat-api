from pydantic import BaseModel, Field
from typing import Literal
import matplotlib.pyplot as plt

AVAILABLE_COLORMAPS = plt.colormaps()
class ColorbarRequest(BaseModel):
    colormap_name: Literal[tuple(AVAILABLE_COLORMAPS)] = Field(
        "plasma",
        description=f"Matplotlib colormap to use. Available options: {', '.join(AVAILABLE_COLORMAPS)}",
    )
    min_dbm: float = Field(
        -130.0,
        description="Minimum dBm value for the colormap (default: -130.0).",
    )
    max_dbm: float = Field(
        -30.0,
        description="Maximum dBm value for the colormap (default: -30.0).",
    )
