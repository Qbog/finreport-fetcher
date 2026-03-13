from __future__ import annotations


def apply_pretty_style():
    """Matplotlib 美化（深色背景 + 中文）。"""

    import matplotlib as mpl
    import matplotlib.pyplot as plt

    # 深色背景
    try:
        plt.style.use("dark_background")
    except Exception:
        pass

    # 字体：尽量找可用中文字体
    candidates = [
        "Microsoft YaHei",
        "PingFang SC",
        "Hiragino Sans GB",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "SimHei",
        "Noto Sans CJK JP",
        "Noto Serif CJK JP",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    mpl.rcParams["font.sans-serif"] = candidates
    mpl.rcParams["axes.unicode_minus"] = False

    bg = "#0B1220"  # 深色背景
    fg = "#E6EDF3"  # 亮色文字
    grid = "#2B3445"

    mpl.rcParams.update(
        {
            "figure.figsize": (12, 6),
            "figure.facecolor": bg,
            "savefig.facecolor": bg,
            "axes.facecolor": bg,
            "axes.edgecolor": fg,
            "axes.labelcolor": fg,
            "axes.titlesize": 16,
            "axes.labelsize": 12,
            "text.color": fg,
            "xtick.color": fg,
            "ytick.color": fg,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "grid.color": grid,
            "grid.alpha": 0.35,
            "legend.fontsize": 10,
        }
    )
