from __future__ import annotations
from typing import List, Optional, Dict
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

def plot_topic_timeline(
    topic_ids: List[int],
    title: str,
    topic_labels: Optional[Dict[int, str]] = None,
    outfile: Optional[str] = None,
):
    arr = np.array(topic_ids)[None, :]

    fig = plt.figure(figsize=(14, 3.2 if topic_labels else 1.6))
    ax = fig.add_subplot(111)

    im = ax.imshow(arr, aspect="auto")
    ax.set_yticks([])
    ax.set_xlabel("Chunk index")
    ax.set_title(title)

    if topic_labels:
        cmap = im.get_cmap()
        norm = im.norm

        handles = []
        for tid in sorted(topic_labels.keys()):
            color = cmap(norm(tid))
            label = f"{tid}: {topic_labels[tid]}"
            handles.append(mpatches.Patch(color=color, label=label))

        ax.legend(
            handles=handles,
            loc="upper left",
            bbox_to_anchor=(0, -0.65),
            ncol=2,
            fontsize=8,
            frameon=False,
        )
        plt.subplots_adjust(bottom=0.45)

    plt.tight_layout()
    if outfile:
        plt.savefig(outfile, dpi=200)
    plt.show()

